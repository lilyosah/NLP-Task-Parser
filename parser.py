from microtc.utils import tweet_iterator
from os.path import join
import spacy
import json

FILE = "tasks.json"
    

def validate(input, output):
    '''
    Visualize differences between input and output dataset and output in "differences.json"
    '''

    differences = []

    for i in range(len(input)):
        input_task = input[i]
        output_task = output[i]
        original = input_task["input"]
        del input_task["input"]
        if input_task != output_task:
            differences.append({"original input": original, "correct groups": input_task, "our output": output_task})
    
    with open("differences.json", "w") as f:
        json.dump(differences, f)
    if len(differences) != 0:
        print("There were", len(differences), "different outputs between the input and output files, check differences.json")

def set_pipes(groups):
    '''
    Set up nlp object with desired pipes.
    
    Pipes that may be helpful: 
    - Attribute ruler - set/override attributes for tokens
    - EntityRecognizer (using) - For dates and times 
    - EntityRules - To add ent types 
    - Lemmatizer - Base forms of words
    - Tokenizer (using I think)
    - merge_entities - Merge named entities into a single token.
    - merge_noun_chunks - Merge noun chunks into a single token.
    '''

    entity_patterns = []
    for group in groups:
        p = [{"LOWER": word} for word in group.split(" ")] 
        ep = {"label": "GROUP", "pattern": p}
        entity_patterns.append(ep)

    nlp = spacy.load("en_core_web_sm", disable=[
        "DependencyParser",
        "EntityLinker",
        "Morphologizer",
        "SentenceRecognizer",
        "Sentencizer", 
        "TextCategorizer",
        "Tok2Vec",
        "TrainablePipe",
        "Transformer"])

    ruler = nlp.add_pipe("entity_ruler")
    ruler.add_patterns(entity_patterns)

    return nlp

def is_date_or_time(token):
    return token.ent_type_ == "DATE" or token.ent_type_ == "TIME"

def include_in_task(token):
    ADP_before_date = token.i + 1 < len(token.doc) and token.pos_ == "ADP" and is_date_or_time(token.nbor())
    in_included_pos = token.pos_ == "VERB" \
                    or token.pos_ == "ADJ" \
                    or token.pos_ == "AUX" \
                    or token.pos_ == "NOUN" \
                    or token.pos_ == "PROPN" \
                    or token.pos_ == "ADP" \
                    or token.pos_ == "ADV" \
                    or token.pos_ == "DET" \
                    or token.pos_ == "PART" \
                    or token.pos_ == "PUNCT" \
                    or token.pos_ == "INTJ"
    is_excluded = token.text == "!"
    
    return in_included_pos and not (ADP_before_date or is_excluded or is_date_or_time(word))

def attached_to_last_word(token):
    '''
    True if token should be appended to the last token
    '''
    return (token.pos_ == "PART" or token.pos_ == "PUNCT") and  ("'" in token.text)

def add_ents(doc, answers):
    for ent in doc.ents:
        if ent.label_ == "GROUP":
            answers["group"] = ent.text
        else:
            if ent.label_ == "DATE":
                answers["date"].append(ent.text)
            if ent.label_ == "TIME":
                answers["time"] = ent.text

if __name__ == "__main__":
    # !!!Make sure you run this: $ python -m spacy download en_core_web_sm
    dataset = json.load(open(FILE))

    # These will be set by the user.
    predefined_groups = ["bio", "cosc", "computer science", "japanese", "English"]

    nlp = set_pipes(predefined_groups)
    
    results = []


    for data in dataset:
        input_task = data["input"]
        doc = nlp(input_task)
        answers = { "group": None, "task": [], "date": [], "time": None }

        add_ents(doc, answers)

        for word in doc:
            if include_in_task(word): 
                if attached_to_last_word(word):
                    answers["task"][-1] += word.text
                else:
                    answers["task"].append(word.text)
            
        
        # Format outputs for validate()
        if len(answers["task"]) != 0:
            answers["task"] = " ".join(answers["task"])
        else: 
            answers["task"] = None
        if len(answers["date"]) == 0:
            answers["date"] = None
        else:
            answers["date"] = " ".join(answers["date"])
        
        results.append(answers)
    
    with open("parsed_tasks.json", "w") as f:
        json.dump(results, f)

    validate(dataset, results)




