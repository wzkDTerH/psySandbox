import csv
import os
import json


def get_file_path():
    n_agent = 16
    n, k, p = 5, 3, 7
    t, ts = 64, 8
    args_str = "NA{}_N{}_K{}_P{}_T{}_Ts{}".format(n_agent, n, k, p, t, ts)
    exp_name = "20181223-010150"
    exp_id = "exp0"
    exp_dir = os.path.join("..", "..", "result",
                           "batch_{exp_name}_{args_str}",
                           "mul_{exp_name}_{exp_id}").format(exp_name=exp_name,
                                                             args_str=args_str,
                                                             exp_id=exp_id)
    input_json_name = "mul_{exp_name}_{exp_id}_leadership_bill.json".format(exp_name=exp_name, exp_id=exp_id)
    output_csv_name = "mul_{exp_name}_{exp_id}_leadership_bill.csv".format(exp_name=exp_name, exp_id=exp_id)
    output_sum_csv_name = "mul_{exp_name}_{exp_id}_leadership_bill_sum.csv".format(exp_name=exp_name, exp_id=exp_id)
    args = {
        "input_json_path": os.path.join(exp_dir, input_json_name),
        "output_csv_path": os.path.join(exp_dir, output_csv_name),
        "output_sum_csv_path": os.path.join(exp_dir, output_sum_csv_name),
        "agent_num": n_agent, "T": t, "Ts": ts
    }
    return args


def get_walk_funcs():

    def func_fatory(assert_lists):
        def _f(jd_list, time, agent_id):
            ret_num = len(jd_list)
            for jd in jd_list:
                for asst in assert_lists:
                    if not asst(jd, time, agent_id):
                        ret_num -= 1
                        break
            return ret_num
        return _f

    assert_lists = {
        'm-plan': [
            lambda jd, ti, id: jd['record_type'] == 'm-plan',
            lambda jd, ti, id: jd['gen']['time'] == ti,
            lambda jd, ti, id: jd['gen']['person'] == id,
            lambda jd, ti, id: jd['gen']['act'] != 'start'
        ],
        'm-info': [
            lambda jd, ti, id: jd['record_type'] == 'm-info',
            lambda jd, ti, id: jd['gen']['time'] == ti,
            lambda jd, ti, id: jd['gen']['person'] == id,
            lambda jd, ti, id: jd['gen']['act'] != 'start'
        ],
        'talking-whlj': [
            lambda jd, ti, id: jd['record_type'] == 'talking',
            lambda jd, ti, id: jd['talking_type'] == 'whlj',
            lambda jd, ti, id: jd['speaker']['time'] == ti,
            lambda jd, ti, id: jd['speaker']['person'] == id,
            lambda jd, ti, id: jd['speaker']['person'] != jd['listener']['person']
        ],
        'talking-dyjs': [
            lambda jd, ti, id: jd['record_type'] == 'talking',
            lambda jd, ti, id: jd['talking_type'] == 'dyjs',
            lambda jd, ti, id: jd['speaker']['time'] == ti,
            lambda jd, ti, id: jd['speaker']['person'] == id,
            lambda jd, ti, id: jd['speaker']['person'] != jd['listener']['person']
        ],
        'talking-m-req-hqxx': [
            lambda jd, ti, id: jd['record_type'] == 'talking',
            lambda jd, ti, id: jd['talking_type'] == 'meet_req',
            lambda jd, ti, id: jd['meeting'] == 'hqxx',
            lambda jd, ti, id: jd['speaker']['time'] == ti,
            lambda jd, ti, id: jd['speaker']['person'] == id,
            lambda jd, ti, id: jd['speaker']['person'] != jd['listener']['person']
        ],
        'talking-m-req-xtfg': [
            lambda jd, ti, id: jd['record_type'] == 'talking',
            lambda jd, ti, id: jd['talking_type'] == 'meet_req',
            lambda jd, ti, id: jd['meeting'] == 'xtfg',
            lambda jd, ti, id: jd['speaker']['time'] == ti,
            lambda jd, ti, id: jd['speaker']['person'] == id,
            lambda jd, ti, id: jd['speaker']['person'] != jd['listener']['person']
        ],
        'talking-m-req-tljc': [
            lambda jd, ti, id: jd['record_type'] == 'talking',
            lambda jd, ti, id: jd['talking_type'] == 'meet_req',
            lambda jd, ti, id: jd['meeting'] == 'tljc',
            lambda jd, ti, id: jd['speaker']['time'] == ti,
            lambda jd, ti, id: jd['speaker']['person'] == id,
            lambda jd, ti, id: jd['speaker']['person'] != jd['listener']['person']
        ],
        'talking-get-plan': [
            lambda jd, ti, id: jd['record_type'] == 'talking',
            lambda jd, ti, id: jd['talking_type'] == 'get_a_plan',
            lambda jd, ti, id: jd['speaker']['time'] == ti,
            lambda jd, ti, id: jd['speaker']['person'] == id,
            lambda jd, ti, id: jd['speaker']['person'] != jd['listener']['person']
        ],
        'talking-commit': [
            lambda jd, ti, id: jd['record_type'] == 'talking',
            lambda jd, ti, id: jd['talking_type'] == 'commit_plan',
            lambda jd, ti, id: jd['speaker']['time'] == ti,
            lambda jd, ti, id: jd['speaker']['person'] == id,
            lambda jd, ti, id: jd['speaker']['person'] != jd['listener']['person']
        ],
        'talking-get_useful_info': [
            lambda jd, ti, id: jd['record_type'] == 'talking',
            lambda jd, ti, id: jd['talking_type'] == 'get_useful_info',
            lambda jd, ti, id: jd['speaker']['time'] == ti,
            lambda jd, ti, id: jd['speaker']['person'] == id,
            lambda jd, ti, id: jd['speaker']['person'] != jd['listener']['person']
        ]
    }

    walk_funcs = [{"name": asst_name, "func": func_fatory(assert_lists[asst_name])}
                  for asst_name in assert_lists]
    return walk_funcs


def fill_tabel_by_json(input_json, args):
    n_agent = args['agent_num']
    total_t = args['T']
    walk_funcs = get_walk_funcs()

    def json_list_key_select(jdata, key, value):
        def _dfs(the_jd):
            for k in the_jd:
                if k == key and the_jd[k] == value:
                    return True
                elif isinstance(the_jd[k], dict) and _dfs(the_jd[k]):
                    return True
            return False
        return [jd for jd in jdata if _dfs(jd)]

    title = ['T', 'agent_no'] + [wkfc['name'] for wkfc in walk_funcs]
    ret_table = []
    for ti in range(total_t):
        t_split_json = json_list_key_select(input_json, 'time', ti)
        for agent_i in range(n_agent):
            t_a_split_json = json_list_key_select(t_split_json, 'person', agent_i)
            new_row = {'T': ti, 'agent_no': agent_i}
            for wkfc in walk_funcs:
                func_name, func = wkfc['name'], wkfc['func']
                new_row[func_name] = func(t_a_split_json, ti, agent_i)
            ret_table.append(new_row)
    return  ret_table, title

def calc_output_sum(csv_table, title, args):
    n_agent = args['agent_num']
    total_t = args['T']
    def row_i(ti, ai):
        return ti * n_agent + ai
    sum_table = []
    for ti in range(total_t):
        for ai in range(n_agent):
            new_row = {'T': ti, 'agent_no': ai}
            for k in title:
                if k == 'T' or k == 'agent_no':
                    continue
                new_row[k] = csv_table[row_i(ti, ai)][k]
                new_row[k] += sum_table[row_i(ti - 1, ai)][k] if ti > 0 else 0
            sum_table.append(new_row)
    return sum_table

def main(args):
    input_json_path = args['input_json_path']
    output_csv_path = args['output_csv_path']
    output_sum_csv_path = args['output_sum_csv_path']

    with open(input_json_path, "r") as fp:
        input_json = json.load(fp)

    output_csv_table, output_title = fill_tabel_by_json(input_json, args)

    output_sum_csv_table = calc_output_sum(output_csv_table,  output_title, args)

    def save_csv(filepath, csv_table, title):
        with open(filepath, "w") as fp:
            csv_d = csv.DictWriter(fp, fieldnames=title, lineterminator="\n")
            csv_d.writeheader()
            csv_d.writerows(csv_table)

    save_csv(output_csv_path, output_csv_table, output_title)
    save_csv(output_sum_csv_path, output_sum_csv_table, output_title)

if __name__ == "__main__":
    args = get_file_path()
    main(args)
