import spacy
import json
import re
import additional_pipelines
from collections import Counter

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
    if answers["task"]:
        answers["task"] = " ".join(answers["task"])
    else: 
        answers["task"] = None

    if answers["date"]:
        answers["date"] = " ".join(answers["date"])
    else:
        answers["date"] = None

    if not answers["recurrence"]:
        answers["recurrence"] = None
    
    if answers["group"]:
        answers["group"] = list(answers["group"])
    else:
        answers["group"] = None

def get_entity_patterns(groups):
    entity_patterns = []
    for group in groups:
        # if the lowercase version of the token matches our word then add it
        p = [{"LOWER": word.lower()} for word in group.split(" ")] 
        ep = {"label": "GROUP", "pattern": p}
        entity_patterns.append(ep)
    for holiday in holidays:
        # if the lowercase version of the token matches our word then add it
        p = [{"LOWER": word.lower()} for word in holiday.split(" ")] 
        ep = {"label": "HOLIDAY", "pattern": p}
        entity_patterns.append(ep)
    return entity_patterns

def get_nlp(exclude_list, groups, holidays):
    nlp = spacy.load("en_core_web_sm", exclude=exclude_list)
    nlp.add_pipe("expand_weekday_dates")
    # Set ER to assign our labels over other entity types
    nlp.add_pipe("entity_ruler", config={"overwrite_ents": True, "phrase_matcher_attr": "LOWER"}).add_patterns(get_entity_patterns(groups))
    nlp.add_pipe("get_recurrence_entities", after="entity_ruler")
    nlp.add_pipe("merge_nouns_without_group", after="get_recurrence_entities")
    return nlp

def is_date_or_time(token):
    #HOLIDAY ent_type_ does not work, it appears as if it is never assigned
    return token.ent_type_ == "DATE" or token.ent_type_ == "TIME" or token.ent_type_ == "HOLIDAY"

def include_in_task(token):
    ADP_before_removed_portion = token.i + 1 < len(token.doc) and token.pos_ == "ADP" and (is_date_or_time(token.nbor()) or token.nbor().ent_type_ == "RECURRENCE")
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
                    or token.pos_ == "INTJ" \
                    or token.pos_ == "PRON" \
                    or token.pos_ == "CCONJ"
    return in_included_pos and not (ADP_before_removed_portion)

def attached_to_last_word(token):
    '''
    True if token should be appended to the last token
    (Should attach to last word if it's a contraction or punctuation)
    '''
    # Includes things like "n't" and "to"
    return (token.pos_ == "PART" and "'" in token.text) or token.pos_ == "PUNCT"

def parse_body(doc, answers):
    for token in doc:
        
        if token.ent_type_ == "RECURRENCE":
            answers["recurrence"] = token.text
        elif token.ent_type_ == "DATE" or token.ent_type_ == "HOLIDAY":
            answers["date"].append(token.text)
        elif token.ent_type_ == "TIME":
            answers["time"] = token.text
        elif include_in_task(token):
            if attached_to_last_word(token):
                answers["task"][-1] += token.text
            else:
                answers["task"].append(token.text)

def groups_from_acronyms(input, abbrev_dict):
    '''
    Finds acronyms or abbreviations for a group name in the user input task
    '''
    abbrev = re.compile("[a-zA-Z]{2,}")
    output = abbrev.findall(input)
    entities = Counter(output)
    found_groups = set()
    
    for key in entities.keys():
        key = str(key).lower()
        for group in predefined_groups:
            # check if it's an acronym or if we have already seen it
            if key in abbrev_dict.get(group):
                found_groups.add(group)
            # check if it's an abbreviation of a group name
            if key[0] == group[0].lower() and key in group.lower():
                abbrev_dict[key] = abbrev_dict.get(group).add(key)
                found_groups.add(group)
    return found_groups

def add_acronyms(groups, abbrev_dict):
    for group in groups:
        group_terms = group.split(" ")
        if len(group_terms) > 1:
            acronym = ""
            for t in group_terms:
                acronym += t[0]
            abbrev_dict[group].add(acronym.lower())

if __name__ == "__main__":
    # !!!Make sure you run this: $ python -m spacy download en_core_web_sm
    holidays = ["Christmas", "Valentine's Day", "Halloween", "Easter", "Passover", "Hanukkah", "New Year's Eve", "New Year's Day", "Diwali", "Eid al-Fitr",
            "Saint Patrick's Day", "Thanksgiving"]

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

    c = ":)"
    while c.lower() != "q":
        # These will be set by the user.
        predefined_groups = input("Please enter groups within quotes separated by pipes: ")
        predefined_groups = predefined_groups.split("|")

        nlp = get_nlp(exclude_list, predefined_groups, holidays)
        abbrev_dict = {group : set() for group in predefined_groups} # keep track of all abbreviations for group names that we have seen
        add_acronyms(predefined_groups, abbrev_dict)

        input_task = input("Task: ")
        doc = nlp(input_task)
        answers = { "group": set(), "task": [], "date": [], "time": None, "recurrence": [] }

        parse_body(doc, answers)

        answers["group"] = groups_from_acronyms(input_task, abbrev_dict)

        format_answers(answers)

        print("\nOutput:")
        print(json.dumps(answers, indent=4, separators=(', ', ': ')))
        
        c = input("Q to quit, anything else to parse another: ")
        print()
    print("Goodbye")
