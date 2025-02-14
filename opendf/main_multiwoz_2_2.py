"""
Main class to run MultiWOZ 2.2 experiments.
"""
import argparse
import json
import logging
import os.path
import time

import yaml

from opendf.applications import EnvironmentClass, MultiWOZContext
from opendf.applications.multiwoz_2_2.conversion import convert_dialogue, convert_dialog_act, normalize_time, \
    ConversionErrorMultiWOZ_2_2, get_related_dict
from opendf.applications.multiwoz_2_2.nodes.multiwoz import MwozConversation, collect_last_state
from opendf.applications.multiwoz_2_2.utils import TIME_REGEX
from opendf.defs import LOG_LEVELS, config_log, EnvironmentDefinition, CONT_TURN, OUTLINE_SIMP, SUGG_IMPL_AGR, SUGG_MSG
from opendf.exceptions import parse_node_exception, re_raise_exc, DFException
from opendf.graph.constr_graph import construct_graph, check_constr_graph
from opendf.graph.draw_graph import draw_all_graphs
from opendf.graph.eval import evaluate_graph, check_dangling_nodes
from opendf.graph.transform_graph import do_transform_graph
from opendf.utils.arg_utils import add_environment_option
from opendf.utils.simplify_exp import indent_sexp
from opendf.utils.utils import to_list, flatten_list
from opendf.defs import is_pos
import re

DATA_FOLDERS = {'train', 'dev', 'test'}

logger = logging.getLogger(__name__)
environment_definitions = EnvironmentDefinition.get_instance()

INDEX_FILENAME = "index_2_2.json"

ALLOW_RECOMMENDED_TRAIN_TIME = True
# SUGGEST_D_ACT_CORRECTIONS = True
# USE_SUGGESTED_D_ACTS = False


def create_index(data_directory, folders):
    index = {}
    for folder in folders:
        files = filter(lambda x: x.endswith('.json'),
                       os.listdir(os.path.join(data_directory, folder)))
        for file in files:
            file_path = os.path.join(data_directory, folder, file)
            with open(file_path) as input_file:
                dialogues = json.load(input_file)
                for i, dialogue in enumerate(dialogues):
                    dialogue_id = dialogue["dialogue_id"]
                    index[dialogue_id] = {"file": file_path, "index": i}

    return index


def get_dialogue_index(dialogue_id, data_directory):
    index_filepath = os.path.join(data_directory, INDEX_FILENAME)
    index = {}
    if os.path.isfile(index_filepath):
        with open(index_filepath) as index_file:
            index = json.load(index_file)
    if not index:
        index = create_index(data_directory, DATA_FOLDERS)
        with open(index_filepath, 'w') as index_file:
            json.dump(index, index_file, indent=4)

    return index.get(dialogue_id)


def get_single_dialogue(dialogue_id, data_directory):
    if not dialogue_id.endswith(".json"):
        dialogue_id += ".json"
    dialogue_index = get_dialogue_index(dialogue_id, data_directory)

    if dialogue_index:
        with open(dialogue_index["file"]) as input_file:
            dialogues = json.load(input_file)
            dialogue = dialogues[dialogue_index["index"]]
            if dialogue["dialogue_id"] == dialogue_id:
                return dialogue
            else:
                logger.warning(f"Index id does not match requested id, is the index file corrupted")
    else:
        logger.warning("Could not find MultiWOZ 2.2 dialogue %s in %s", dialogue_id, data_directory)

    return None


def find_dialogue(dialogue_id, data_directory):
    results = []
    if dialogue_id in DATA_FOLDERS:
        folder = dialogue_id
        files = filter(lambda x: x.endswith('.json'),
                       os.listdir(os.path.join(data_directory, folder)))
        for file in files:
            file_path = os.path.join(data_directory, folder, file)
            with open(file_path) as input_file:
                dialogues = json.load(input_file)
                results.extend(dialogues)
    else:
        single_dialogue = get_single_dialogue(dialogue_id, data_directory)
        if single_dialogue:
            results.append(single_dialogue)

    return results


def create_arguments_parser():
    """
    Creates the argument parser for the file.

    :return: the argument parser
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        description="The main entry point to run MultiWOZ 2.2 dialogues.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--data_dir", "-i", metavar="config", type=str, required=False, default="tmp/multiwoz_2_2",
        help="MultiWOZ 2.2 data directory"
    )

    parser.add_argument(
        "--config", "-c", metavar="config", type=str, required=False, default="resources/multiwoz_2_2_config.yaml",
        help="the configuration file for the application"
    )

    parser.add_argument(
        "--dialog_id", "-d", metavar="dialog_id", type=str, required=False, default="dev",
        help="a list of dialogue ids, or the name of a dialogue folder to be used to use.",
        nargs="+"
    )

    parser.add_argument(
        "--start_from", "-f", metavar="start_from", type=str, required=False, default=None,
        help="start from with this dialog (useful for debugging)"
    )

    parser.add_argument(
        "--write_state", "-w", metavar="write_state", type=str, required=False, default=None,
        help="name of file to write DF state into"
    )

    parser.add_argument(
        "--services", "-s", metavar="services", type=str, required=False,
        default=['hotel', 'police', 'hospital', 'attraction', 'restaurant', 'taxi', 'train'],
        help="Select services - only dialogs with these services (domains) will be run. use '-s dom1 dom2' to select"
             "all dialogs with dom1 and/or dom2. '-s dom1/dom2' to select all dialogs with dom1 AND dom2, (and possibly"
             "other domains as well). '-s dom1:dom2' - select only dialogs with dom1 and dom2 (and no other domains)",
             nargs="+"
    )

    parser.add_argument(
        "--patch", "-p", metavar="services", type=str, required=False, default='',
        help="specify an annotation patch file "
    )

    parser.add_argument(    # load only some services (not so relevant now, since we use a DB for search)
        "--load_services", "-l", metavar="load_services", type=str, required=False,
        default=['hotel', 'police', 'hospital', 'attraction', 'restaurant', 'taxi', 'train'],
        help="The services whose data should be loaded. It will only load data for the listed "
             "services, the default is to only the services from the dialogue", nargs="+"
    )

    parser.add_argument(
        "--output", "-o", metavar="output", type=str, required=False, default="",
        help="Output directory for the result files"
    )

    parser.add_argument(
        "--log", "-log", metavar="log", type=str, required=False, default="DEBUG",
        choices=LOG_LEVELS.keys(),
        help=f"The level of the logging, possible values are: {list(LOG_LEVELS.keys())}"
    )

    parser.add_argument(
        "--use_dialog_act", "-a", required=False,
        default=False, action="store_true",
        help=f"Use dialog acts instead of state"
    )

    parser.add_argument(
        "--draw_graph", "-g", required=False,
        default=False, action="store_true",
        help=f"Draw graph (when running one dialog)"
    )

    parser.add_argument(
        "--agent_oracle", "-A", required=False,
        default=False, action="store_true",
        help=f"use agent oracle values"
    )

    parser.add_argument(
        "--oracle_only", "-O", required=False,
        default=False, action="store_true",
        help=f"if use agent oracle, use only the oracle - ignore node logic completely"
    )

    parser.add_argument(
        "--stop_exc", "-x", required=False,
        default=False, action="store_true",
        help=f"Stop execution on non-DF exceptions"
    )

    parser = add_environment_option(parser)

    return parser


def get_user_trans(dialogue, turn, context, use_dialog_act=False):
    try:
        expression, conv_problems = convert_dialogue(dialogue, turn, context, use_dialog_act=use_dialog_act)
        d, cont = expression, False
        if d.startswith(CONT_TURN):
            d, cont = d[2:], True
        return d, cont, conv_problems
    except Exception as e:
        raise ConversionErrorMultiWOZ_2_2(f"Exception {e} raised during conversion", e)


def lenient_name_match(a, b):
    if a==b or a in b or b in a:
        return True
    a = a.lower().split()
    b = b.lower().split()
    for w in a:
        if w not in ('the', 'hotel', 'house') and w in b:
            return True
    return False




# match values depending on type
def match_values(v, lv, name):
    if not v or 'request' in name:
        return True
    if v in lv:
        return True
    if '-name' in name and any([lenient_name_match(v, l) for l in lv]):
        return True
    return False


def to_time_vals(t):
    if isinstance(t, str):
        if t.lower()=='lunch':
            t = '12:00'
        match = TIME_REGEX.fullmatch(t)
        if match:
            hour, minute = match.groups()
            return int(hour) % 24, int(minute) % 60
    return None, None


# t1 <= t2
def time_le(t1, t2):
    h1, m1 = to_time_vals(t1)
    h2, m2 = to_time_vals(t2)
    if h1 is not None and h2 is not None:
        return h1>h2 or (h1==h2 and m1>m2)
    return None


# tried - is a state mismatch always (or even a majority of cases) a result of a wrong dialog act annotation?
#         limited manual inspection does not support that - both state and dialog act annotations can have errors
# def make_missing_slot_sugg(service, name, values, slot_dict, d_acts, utter):
#     # unless the missing slot already exists in the dialog acts, then suggest adding the slot
#     dname = service.capitalize() + '-Inform'
#     if dname not in d_acts or name not in d_acts[dname]:
#         return [(service, name.split('-')[-1], to_list(values)[0], utter)]
#     return []


def compare_dialogue_state(multiwoz_state, df_state, p_expression, use_dialog_act=False):
    """
    Compares the current DF State with the expected dialogue state from the MultiWOZ 2.2 Dataset.

    :param multiwoz_state: the MultiWOZ state
    :type multiwoz_state: dict
    :param df_state: the DF state
    :type df_state: dict
    :param p_expression: the current P-Expression
    :type p_expression: str
    :return: List[str]
    :rtype: the list of differences between the current and the expected states
    """
    errors = []
    mw_active_intents = set()
    # sugg_corr = []

    mw_turn_id = multiwoz_state["turn_id"]
    df_turn_id = df_state["turn_id"]
    # d_acts = multiwoz_state['dialog_act']['dialog_act']
    if mw_turn_id != df_turn_id:
        errors.append(
            f"<TURN ID MISMATCH> Turn id {mw_turn_id} from MultiWOZ does not match turn id {df_turn_id} from DF")

    for mw_frame in multiwoz_state.get("frames", []):
        active_intent = mw_frame.get("state", {}).get("active_intent", "NONE")
        if active_intent == "NONE":
            continue
        mw_active_intents.add(active_intent)
        service = mw_frame.get("service")
        df_frame = get_related_dict(service, df_state.get("frames", []))
        df_slot_values = df_frame.get("state", {}).get("slot_values", {})
        # if False and use_dialog_act:  # TODO - this will be removed
        #     slot_dict = convert_dialog_act(multiwoz_state, service)
        # else:
        slot_dict = mw_frame.get("state", {}).get("slot_values", {})
        for name, values in slot_dict.items():
            df_value = df_slot_values.get(name)
            if df_value is None and 'request' not in name:
                errors.append(
                    f"{mw_turn_id} <SLOT NOT FOUND> Service: {service}, Turn: {mw_turn_id}, slot \"{name}\" not found in DF state")
                # if SUGGEST_D_ACT_CORRECTIONS:
                #     sugg_corr += make_missing_slot_sugg(service, name, values, slot_dict, d_acts, multiwoz_state['utterance'])
                continue
            if "dontcare" in values:
                # in this case, the DF slot must be present, but its value does not matter
                # TODO: should we also allow missing value in the DF context
                continue
            if isinstance(df_value, list) and len(df_value) > 0:
                if df_value:
                    df_value = df_value[0]
            if name.endswith("leaveat") or name.endswith("arriveby"):
                values = list(map(lambda x: normalize_time(x), to_list(values)))
                df_value = normalize_time(df_value)
            if not match_values(df_value, values, name):
                if ALLOW_RECOMMENDED_TRAIN_TIME and name in ['train-leaveat', 'train-arriveby'] \
                        and 'train-trainid' in df_slot_values:
                    if (name=='train-leaveat' and any([time_le(df_value,v) for v in to_list(values)])) or \
                            (name == 'train-arriveby' and any([time_le(v,df_value) for v in to_list(values)])):
                        continue
                    x=1
                errors.append(f"{mw_turn_id} <WRONG SLOT VALUE> Service: {service}: value \"{df_value}\" for slot \"{name}\" "
                f"at turn {mw_turn_id} not in the list of possible values: {values}")
                x=1

    turn_number = int(df_turn_id) / 2
    if errors:
        logger.warning("Errors for turn %d:\n%s\n", turn_number, "\n".join(errors))
    else:
        logger.info("No errors for turn %d!", turn_number)

    return errors  # , sugg_corr


def break_cont_exps(g):
    if g.typename()=='cont_turn':
        return flatten_list([break_cont_exps(g.inputs[i]) for i in g.inputs if is_pos(i)])
    else:
        return [g]


def dialog(dialogue, d_context, draw_graph=True, use_dialog_act=False, patch=None):
    """
    This main function gets P-exps as input, and executes them one by one.
    The input is taken from `dialogs` in `opendf.examples.main_examples.py`.

    :param dialogue: the dialogue, in MultiWOZ 2.2 format
    :type dialogue: Dict
    :param d_context: The dialog context
    :type d_context: MultiWOZContext
    :param draw_graph: if `True`, it will draw the resulting graph
    :type draw_graph: bool
    :return: Tuple[Node, Optional[Exception]]
    :rtype: the generated graph and the exception, if exists
    """
    end_of_dialog = False
    d_context.reset_turn_num()
    ex = None
    psexp = None  # prev sexp
    i_utter = 0
    all_conv_problems = []
    all_execution_problems = []
    all_expressions = []
    all_answers = []
    # all_sugg_corr = []

    dialogue_id = dialogue["dialogue_id"]
    logger.info("dialog %s", dialogue_id)
    gl = None
    while not end_of_dialog:
        # 1. get user processed input (sexp format)
        isexp, cont, conv_problems = get_user_trans(
            dialogue, i_utter, d_context, use_dialog_act=use_dialog_act)
        pid = '%s_%d' % (re.sub('.json', '', dialogue_id), i_utter*2)
        if patch and pid in patch:
            isexp = patch[pid]
        all_conv_problems.extend(conv_problems)
        all_expressions.append(isexp)
        if isexp is None:
            break

        logger.info(isexp)

        if environment_definitions.clear_exc_each_turn:
            d_context.clear_exceptions()
        if environment_definitions.clear_msg_each_turn:
            d_context.reset_messages()

        d_context.agent_turn = dialogue['turns'][i_utter * 2 + 1]

        # 2. construct new graph - perform SOME syntax checks on input program.
        #    if something went wrong (which means natural language method sent a wrong sexp) -
        #       no goal was added to the dialog (it was discarded) - user can't help resolve this
        #    if no exception, then a goal has been added to the dialog
        psexp = isexp
        ogl, ex = construct_graph(isexp, d_context, constr_tag=OUTLINE_SIMP, no_post_check=True)

        mgl = break_cont_exps(ogl)
        turn_ans = []
        for ix, igl in enumerate(mgl):
            cont = ix<len(mgl)-1

            # apply implicit accept suggestion if needed. This is when prev turn gave suggestions, and one of them was
            #   marked as implicit-accept (SUGG_IMPL_AGR) (i.e. apply it if the user moves to another topic without accept or reject)
            # do this BEFORE transform_graph - since transform_graph may look at context.goals  (e.g. for side_task)
            if d_context.prev_sugg_act:
                j = [s[2:] for s in d_context.prev_sugg_act if s.startswith(SUGG_IMPL_AGR)]
                if j and not isexp.startswith('AcceptSuggestion') and not isexp.startswith('RejectSuggestion'):
                    sx, ms = j[0], None
                    if SUGG_MSG in sx:
                        s = sx.split(SUGG_MSG)
                        sx, ms = s[0], s[1]
                    gl0, ex0 = construct_graph(sx, d_context)
                    if ex0 is None:
                        if not gl.contradicting_commands(gl0):
                            evaluate_graph(gl0)
                            if ms:
                                d_context.add_message(gl0, ms)

            gl, ex = do_transform_graph(igl)

            check_constr_graph(gl)

            # 3. evaluate graph
            if ex is None:
                ex = evaluate_graph(gl)  # send in previous graphs (before curr_graph added)

            answer = None
            if ex:
                answer = to_list(ex)[0].message
            else:
                answer = d_context.goals[-1].yield_msg()
                # if isinstance(answer, tuple):
                #     answer = answer[0]
                answer = answer.text
            if not answer:
                answer = ''
            turn_ans.append(answer)

            # unless a continuation turn, save last exception (agent's last message + hints)
            d_context.set_prev_agent_turn(ex)

            # 4. answer user: generate message to user, and modify graph to reflect given answer
            # end_of_dialog = i_utter * 2 >= len(dialogue["turns"])

        collect_last_state(d_context)

        # 5. evaluate the result of DF with the state of the dialogue from the dataset
        #    do this after executing ALL the pexps for this turn
        turn_problems = compare_dialogue_state(   # , sugg_corr
            dialogue["turns"][i_utter * 2], d_context.dialog_state["turns"][i_utter], isexp,
            use_dialog_act=use_dialog_act)

        all_answers.append(turn_ans)
        all_execution_problems.extend(turn_problems)
        # all_sugg_corr.extend(sugg_corr)
        i_utter += 1
        d_context.inc_turn_num()
        end_of_dialog = i_utter * 2 >= len(dialogue["turns"])
        check_dangling_nodes(d_context)  # sanity check - debug only
        if environment_definitions.turn_by_turn and not end_of_dialog:
            if draw_graph:
                draw_all_graphs(d_context, dialogue_id)
            input()

    if draw_graph:
        draw_all_graphs(d_context, dialogue_id, ex is None, sexp=indent_sexp(psexp))

    # if d_context.exceptions:
    #     msg, nd, _, _ = parse_node_exception(d_context.exceptions[-1])
    #     nd.explain(msg=msg)

    return gl, ex, all_conv_problems, all_execution_problems, all_expressions, all_answers


def main(dialogue, environment_class: EnvironmentClass, draw_graph=True, load_services=None,
         use_dialog_act=False, patch=None, save_state=None):
    if dialogue is None:
        return
    try:
        d_context: MultiWOZContext = environment_class.get_new_context()
        environment_class.d_context = d_context

        environment_class.domains = load_services if load_services else dialogue["services"]
        with environment_class:
            gl, ex, conversion_problems, execution_problems, expressions, answers = dialog(
                dialogue, d_context, draw_graph=draw_graph, use_dialog_act=use_dialog_act, patch=patch)

            if save_state is not None:
                save_state[dialogue['dialogue_id']] = d_context.dialog_state["turns"]
            return gl, ex, conversion_problems, execution_problems, expressions, answers
    except Exception as e:
        if save_state is not None:
            save_state[dialogue['dialogue_id']] = d_context.dialog_state["turns"]
        raise e


def append_dialogue_act(dialogues, data_dir):
    acts_filepath = os.path.join(data_dir, "dialog_acts.json")
    if not os.path.isfile(acts_filepath):
        raise FileNotFoundError(f"Could not find the dialog_acts.json in {data_dir}")

    with open(acts_filepath) as acts_file:
        dialog_acts = json.load(acts_file)
        for dialogue in dialogues:
            dialogue_id = dialogue["dialogue_id"]
            dialog_act = dialog_acts.get(dialogue_id)
            if not dialog_act:
                continue
            for turn in dialogue["turns"]:
                turn_act = dialog_act.get(turn["turn_id"])
                if turn_act:
                    turn["dialog_act"] = turn_act

    return dialogues


# annotation patch file - has lines of the format:
# dialog_id turn_num  pexp
# for now, we only allow patches to user turns (but  patches for agent could also make sense!)
# We use this patch to replace an automatically generated Pexp by the one given in the patch file.
#   - note - this is done in order to fix annotation problems.
#            (using pexp is more convenient than modifying the annotation file, as well as keeping the patches separate)
def load_patch(nm):
    patch = {}
    if nm:
        for l in open(nm, 'r').readlines():
            s = l.split()
            n = re.sub('\.json', '', s[0])
            patch[n+'_'+s[1]] = ' '.join(s[2:])
    return patch

if __name__ == '__main__':
    start = time.time()
    try:
        parser = create_arguments_parser()
        arguments = parser.parse_args()
        config_log(level=arguments.log)
        id_arg = arguments.dialog_id
        if isinstance(id_arg, list):
            single_dialog = not any([i in ['dev', 'train', 'test'] for i in id_arg])
        else:
            single_dialog = id_arg not in ['dev', 'train', 'test']
        data_dir = arguments.data_dir
        services = set(arguments.services)
        service_and, service_exact = False, False
        if len(services)==1 and '/' in list(services)[0]:
            services = set(list(services)[0].split('/'))
            service_and = True
        if len(services)==1 and ':' in list(services)[0]:
            services = set(list(services)[0].split(':'))
            service_exact = True
        load_services = set(arguments.load_services) if arguments.load_services else set()
        output_path = arguments.output
        use_dialog_act = arguments.use_dialog_act
        agent_oracle = arguments.agent_oracle
        oracle_only = arguments.oracle_only
        draw_graph = arguments.draw_graph
        start_from = arguments.start_from
        stop_on_exc = arguments.stop_exc
        write_state = arguments.write_state
        draw_graph = draw_graph and single_dialog  # disable draw unless single dialog
        patch = arguments.patch
        patch = load_patch(patch) if patch else None
        save_state = {} if write_state else None

        if arguments.environment:
            environment_definitions.update_values(**arguments.environment)

        environment_definitions.agent_oracle, environment_definitions.oracle_only = agent_oracle, oracle_only

        application_config = yaml.load(open(arguments.config, 'r'), Loader=yaml.UnsafeLoader)

        good_output_path = output_path + "dialogue_good.txt"
        bad_output_path = output_path + "dialogue_bad.txt"
        json_output_path = output_path + "dialogue.jsonl"
        json_bad_output_path = output_path + "dialogue_bad.jsonl"
        good_dialogues = 0
        bad_dialogues = 0
        n_turns = 0

        saw_start_from = False
        with open(good_output_path, "w") as good_file, open(bad_output_path, "w") as bad_file, open(
                json_output_path, "w") as json_file, open(json_bad_output_path, "w") as json_file_bad:
            for i in id_arg:
                dialogues = find_dialogue(i, data_dir)
                if use_dialog_act:
                    dialogues = append_dialogue_act(dialogues, data_dir)
                for dialogue in dialogues:
                    d_id = dialogue['dialogue_id'].split('.')[0]
                    if start_from:
                        if d_id == start_from:
                            saw_start_from = True
                        if not saw_start_from:
                            continue
                    try:
                        # some dialogues do not have the dialogue["service"] information,
                        # resulting in an empty dialogue["service"]. For now, we filter those out,
                        # but we might want to include then in the future
                        # if not dialogue["services"] or not services.issuperset(dialogue["services"]):
                        if service_and and not all([i in dialogue["services"] for i in services]):
                            continue
                        if service_exact and (len(services)!=len(dialogue["services"]) or \
                                not all([i in dialogue["services"] for i in services])):
                            continue
                        if not services.issuperset(dialogue["services"]):
                            continue
                        n_turns += len(dialogue['turns'])//2
                        _, _, conversion_problems, execution_problems, expressions, answers = main(
                            dialogue, application_config["environment_class"], draw_graph=draw_graph,
                            load_services=load_services, use_dialog_act=use_dialog_act, patch=patch,
                            save_state=save_state)

                        if not conversion_problems and not execution_problems:
                            good_file.write(f"Dialogue {dialogue['dialogue_id']}: OK!\n")
                            # todo - add user/text
                            good_file.write(f"\tExpressions:\n")
                            for ie, expression in enumerate(expressions):
                                good_file.write('\t\t%d. %s\n' % (ie * 2, dialogue['turns'][ie * 2]['utterance']))
                                good_file.write('\t\t%s\n' % expression)
                                good_file.write('\t\t   %s\n' % dialogue['turns'][ie * 2 + 1]['utterance'])
                                good_file.write('\t\t     < %s >\n' % answers[ie])

                            json.dump({"dialogue_id": dialogue["dialogue_id"], "expressions": expressions}, json_file)
                            json_file.write("\n")
                            good_dialogues += 1
                        else:
                            if expressions:
                                json.dump({"dialogue_id": dialogue["dialogue_id"], "expressions": expressions}, json_file_bad)
                                json_file_bad.write("\n")
                            bad_file.write(f"Dialogue {dialogue['dialogue_id']}:\n")
                            # todo - add user/text
                            bad_file.write(f"\tExpressions:\n")
                            for ie, expression in enumerate(expressions):
                                bad_file.write('\t\t%d. %s\n' % (ie * 2, dialogue['turns'][ie * 2]['utterance']))
                                bad_file.write('\t\t%s\n' % expression)
                                bad_file.write('\t\t   %s\n' % dialogue['turns'][ie * 2 + 1]['utterance'])
                                bad_file.write('\t\t     < %s >\n' % answers[ie])
                            if conversion_problems:
                                bad_file.write(f"\tConversion Problems:\n")
                                for conversion_problem in conversion_problems:
                                    bad_file.write("\t\t")
                                    bad_file.write(conversion_problem)
                                    bad_file.write("\n")
                            if execution_problems:
                                bad_file.write(f"\tExecution Problems:\n")
                                for execution_problem in execution_problems:
                                    bad_file.write("\t\t<PROB> %s  " % d_id)
                                    bad_file.write(execution_problem)
                                    bad_file.write("\n")
                            bad_file.write("\n")
                            bad_dialogues += 1
                    except Exception as ex:
                        logger.warning("Error during execution of dialogue %s: %s",
                                       dialogue['dialogue_id'], ex)
                        bad_file.write(f"Dialogue {dialogue['dialogue_id']}:\n")
                        bad_file.write(f"\tError: {ex}\n")
                        # bad_file.write(f"\t\t")
                        # bad_file.write(traceback.format_exc().replace("\n", "\n\t\t").strip())
                        # bad_file.write("\n")
                        # bad_file.write("\n")
                        bad_dialogues += 1
                        if stop_on_exc and not isinstance(ex, DFException):
                            re_raise_exc(ex)

            good_file.write(f"\nTotal of good dialogues: {good_dialogues}\n")
            bad_file.write(f"\nTotal of bad dialogues: {bad_dialogues}\n")
            print(f"\nTotal of good dialogues: {good_dialogues}")
            print(f"\nTotal of bad dialogues: {bad_dialogues}")
            print(f"\nTotal number of user turns: {n_turns}")
    except Exception as e:
        raise e
    finally:
        if write_state:
            open(write_state, 'w').write(json.dumps(save_state))
        end = time.time()
        logger.info(f"Running time: {end - start:.3f}s")
        logging.shutdown()
