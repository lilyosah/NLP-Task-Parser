from microtc.utils import tweet_iterator
from os.path import join
import spacy
import json

FILE = "tasks.json"
    

def validate(input, output, total_inputs):
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
        json.dump(differences, f, indent=4, separators=(', ', ': '))
    if len(differences) != 0:
        print("There were", str(len(differences)) + "/" + str(total_inputs), "different outputs between the input and output files, check differences.json")

def format_answers(answers):
    '''
    Format outputs for validate()
    '''
    if len(answers["task"]) != 0:
        answers["task"] = " ".join(answers["task"])
    else: 
        answers["task"] = None
    if len(answers["date"]) == 0:
        answers["date"] = None
    else:
        answers["date"] = " ".join(answers["date"])
    if len(answers["recurrence"]) != 0:
        answers["recurrence"] = " ".join(answers["recurrence"])
    else: 
        answers["recurrence"] = None


@spacy.Language.component("expand_dates")
def expand_dates(doc):
    new_dates = []
    orig_ents = list(doc.ents)
    for ent in doc.ents:
        if ent.label_ == "ORDINAL":
            if ent.start != 0:
                prev_token = doc[ent.start - 1]
                if prev_token.text == "the":
                    new_ent = spacy.tokens.Span(doc, ent.start - 1, ent.end, label="DATE")
                else:
                    continue
            else: 
                continue
            orig_ents.remove(ent)
            new_dates.append(new_ent)
    if new_dates:
        doc.set_ents(orig_ents + new_dates)
    return doc

@spacy.Language.component("get_recurrence_entities")
def get_recurrence_entities(doc):
    recurrences = []
    if "every" in doc.text:
        print([token.text + ": " + token.label_ for token in doc.ents], doc.text)

    return doc


def get_nlp_with_er(groups, exclude_list):
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
        # if the lowercase version of the token matches our word then add it
        p = [{"LOWER": word.lower()} for word in group.split(" ")] 
        ep = {"label": "GROUP", "pattern": p}
        entity_patterns.append(ep)

    nlp = spacy.load("en_core_web_sm", exclude=exclude_list)

    # Set ER to assign our groups over other entity types
    ruler = nlp.add_pipe("entity_ruler", config={"overwrite_ents": True, "phrase_matcher_attr": "LOWER"}, after="ner")
    ruler.add_patterns(entity_patterns)
    # Add recurrence pipe
    nlp.add_pipe("expand_dates")
    nlp.add_pipe("get_recurrence_entities", after="expand_dates")
    return nlp


def get_nlp_with_noun(exclude_list):
    nlp = spacy.load("en_core_web_sm", exclude=exclude_list)
    nlp.add_pipe("merge_noun_chunks")
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
    
    return in_included_pos and not (ADP_before_date or is_date_or_time(token))

def attached_to_last_word(token):
    '''
    True if token should be appended to the last token
    (Should attach to last word if it's a contraction or punctuation)
    '''
    # Includes things like "n't" and "to"
    return (token.pos_ == "PART" and "'" in token.text) or token.pos_ == "PUNCT"

def add_ents(doc, answers):
    for ent in doc.ents:
        if ent.label_ == "GROUP":
            answers["group"] = ent.text
        elif ent.label == "RECURRENCE":
            answers["recurrence"] = ent.text
        else:
            if ent.label_ == "DATE":
                answers["date"].append(ent.text)
            if ent.label_ == "TIME":
                answers["time"] = ent.text

def add_task_body(doc, answers):
    for word in doc:
        if include_in_task(word): 
            if attached_to_last_word(word):
                answers["task"][-1] += word.text
            else:
                answers["task"].append(word.text)

if __name__ == "__main__":
    # !!!Make sure you run this: $ python -m spacy download en_core_web_sm
    dataset = json.load(open(FILE))

    # These will be set by the user.
    predefined_groups = ["Bio", "Cosc", "Computer Science", "Japanese", "English"]

    # Pipes we don't need
    exclude_list = [
        "DependencyParser",
        "EntityLinker",
        "Morphologizer",
        "SentenceRecognizer",
        "Sentencizer", 
        "TextCategorizer",
        "Tok2Vec",
        "TrainablePipe",
        "Transformer"]

    er_nlp = get_nlp_with_er(predefined_groups, exclude_list)
    noun_nlp = get_nlp_with_noun(exclude_list)

    results = []

    for data in dataset:
        input_task = data["input"]
        er_doc = er_nlp(input_task)
        noun_doc = noun_nlp(input_task)
        answers = { "group": None, "task": [], "date": [], "time": None, "recurrence": [] }

        add_ents(er_doc, answers)
        add_task_body(noun_doc, answers)

        format_answers(answers)
        
        results.append(answers)
    
    with open("parsed_tasks.json", "w") as f:
        json.dump(results, f, indent=4, separators=(', ', ': '))
        
    validate(dataset, results, total_inputs=len(dataset))


# expand date to include days, number of days, 14th (ORDINAL?)
# from every / each to last date/time ent

# counter cases:
# - Do each problem in HW set on friday 
# - Do every HW assignment on Friday

# Every is a DET POS