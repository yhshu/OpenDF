import json


def dialogue_lisp(input_path: str, output_path: str):
    res = []
    # read SMCalFlow jsonl file: https://github.com/microsoft/task_oriented_dialogue_as_dataflow_synthesis/tree/master/datasets/SMCalFlow%202.0
    with open(input_path, 'r') as f:
        lines = f.readlines()
        for line in lines:
            item = json.loads(line)
            dialogue = []
            for turn in item['turns']:
                dialogue.append(turn['lispress'])
            res.append(dialogue)

    with open(output_path, 'w') as f:
        json.dump(res, f)


if __name__ == "__main__":
    dialogue_lisp('train.dataflow_dialogues.jsonl', 'simplify_examples_smcalflow_train.json')
    dialogue_lisp('valid.dataflow_dialogues.jsonl', 'simplify_examples_smcalflow_valid.json')
    print('done')
