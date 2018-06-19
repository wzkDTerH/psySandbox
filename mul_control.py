# -*- coding:utf-8 -*-
import logging
import arg
from group import Group, SoclNet
from env import Env, Area, State
from agent import Agent
from copy import deepcopy
import brain
import meeting
from util.config import all_config
from util import moniter
from record import Record


class MulControl:
    def __init__(self):
        # 环境初始化
        self.global_arg = arg.init_global_arg()
        env_arg = arg.init_env_arg(self.global_arg)
        self.main_env = Env(env_arg)
        # 个体初始化
        self.agents = []
        state_start = State([0] * self.main_env.N)
        for i in range(self.global_arg["Nagent"]):
            self.agents.append(Agent(arg.init_agent_arg(self.global_arg,
                                                        self.main_env.arg),
                                     self.main_env))
            self.agents[i].state_now = deepcopy(state_start)
        # 社会网络初始化
        soclnet_arg = arg.init_soclnet_arg(self.global_arg, env_arg)
        self.socl_net = SoclNet(soclnet_arg)
        self.socl_net.flat_init()
        self.record = Record()

    def run_meet_frame(self, Ti, Tfi, meet_name, member, host, up_info):
        # 根据m_name开会
        self.agents, self.socl_net = meeting.meet_map[meet_name](env=self.main_env,
                                                                 agents=self.agents,
                                                                 member=member,
                                                                 host=host,
                                                                 socl_net=self.socl_net,
                                                                 record=self.record,
                                                                 T=Ti, Tfi=Tfi)

    def run_all_frame(self, Ti, Tfi, meet_req, up_info):
        # 将每个Agent上一帧的初始拷贝进来
        for i in range(len(self.agents)):
            last_arg = deepcopy(self.agents[i].frame_arg)
            # logging.debug("agent %d, %s"%(i,"{}".format(self.agents[i].frame_arg)))
            self.agents[i].frame_arg = arg.init_frame_arg(
                global_arg=self.global_arg,
                env_arg=self.main_env.arg,
                agent_arg=self.agents[i].agent_arg,
                stage_arg=self.agents[i].stage_arg,
                last_arg=last_arg,
                Tp=Ti,
                PSMfi=self.main_env.getValue(self.agents[i].state_now, Ti)
            )

        # 读取之前发起的集体行动
        all_host = set()
        all_meet_info = {}
        new_meet_req = {}
        # 把每一种meeting的host先集中起来，并加入到对应的meet_info中
        # meet_req的结构大致如下？
        # meet_req={
        #    "m_name1":{agent}
        #    "m_name2":{agent}
        # }
        # m_name是指信息交流xxjl之类的集体行动名称

        for m_name in meet_req:
            all_host = all_host.union(meet_req[m_name])
            all_meet_info[m_name] = {"member": meet_req[m_name],
                                     "host": meet_req[m_name]}
        # 询问每个Agent是否加入
        for i in range(len(self.agents)):
            #            logging.debug("all_host:{}".format(all_host))
            # 跳过所有host
            if i in all_host:
                continue
            # 返回是否参与集体行动的信息，如果不参与，执行完个体行动，如果参与,进入后续run_meet_frame
            self.agents[i], self.socl_net, meet_info = brain.mul_agent_act(env=self.main_env,
                                                                           soc_net=self.socl_net,
                                                                           agent=self.agents[i],
                                                                           Ti=Ti, Tfi=Tfi, agent_no=i,
                                                                           record=self.record,
                                                                           meet_req=meet_req)
            if meet_info is None:
                continue
            # 选择参加会议，则加入会议名单
            if meet_info['type'] == 'commit':
                all_meet_info[meet_info['name']]["member"].add(i)
            # 选择发起新会议
            if meet_info['type'] == 'req':
                if not meet_info['name'] in new_meet_req:
                    new_meet_req[meet_info['name']] = set()
                new_meet_req[meet_info['name']].add(i)
        # 每个host都选完人之后，依次开会
        for m_name in all_meet_info:
            self.run_meet_frame(Ti, Tfi, m_name,
                                all_meet_info[m_name]['member'],
                                all_meet_info[m_name]['host'],
                                up_info)
        return new_meet_req

    def run_stage(self, Ti, up_info):
        # 将Agent上一个stage的最终状态拷贝过来
        for i in range(len(self.agents)):
            last_arg = deepcopy(self.agents[i].stage_arg)
            self.agents[i].stage_arg = arg.init_stage_arg(self.global_arg,
                                                          self.main_env.arg,
                                                          self.agents[i].agent_arg,
                                                          last_arg,
                                                          Ti)
        meet_req = {}
        self.record.add_env_record(self.main_env, Ti)
        self.record.add_socl_net_record(self.socl_net, Ti)
        for i in range(self.global_arg['Ts']):
            logging.info("frame %3d , Ti:%3d" % (i, Ti))
            self.record.add_agents_record(self.main_env, self.agents, Ti + i)
            # 运行Frame， 并将运行后生成的会议请求记录下来
            meet_req = self.run_all_frame(Ti, i, meet_req, up_info)

            # 将信息添加到各个结果CSV中
            for k in range(self.global_arg["Nagent"]):
                csv_info = [
                    Ti + i,
                    self.main_env.getValue(self.agents[k].state_now, Ti),
                    up_info['nkinfo']['max'],
                    up_info['nkinfo']['min'],
                    up_info['nkinfo']['avg']
                ]
                moniter.AppendToCsv(csv_info, all_config['result_csv_path'][k])
            agent_value = [self.main_env.getValue(self.agents[k].state_now, Ti) for k in
                           range(self.global_arg["Nagent"])]
            csv_info = [Ti + i] \
                       + agent_value \
                       + [sum(agent_value) / len(agent_value)] \
                       + [up_info['nkinfo'][key] for key in ['max', 'min', 'avg']]
            moniter.AppendToCsv(csv_info, all_config['result_csv_path'][-1])

            net_title, net_data = self.record.output_socl_net_per_frame(Ti + i)
            if (Ti + i == 1):
                moniter.AppendToCsv(net_title, all_config['network_csv_path'])
            moniter.AppendLinesToCsv(net_data, all_config['network_csv_path'])
            #  P1-05 增加Socil Network的结果输出

    def run_exp(self):
        up_info = {}

        # 单个agent的结果文档
        for k in range(self.global_arg["Nagent"]):
            csv_head = ['frame', 'SSMfi', 'nkmax', 'nkmin', 'nkavg']
            moniter.AppendToCsv(csv_head, all_config['result_csv_path'][k])
        # 汇总结果文档
        csv_head = ['frame'] \
                   + ["agent%d" % (k) for k in range(self.global_arg['Nagent'])] \
                   + ["agent_avg"] \
                   + ['nkmax', 'nkmin', 'nkavg']
        moniter.AppendToCsv(csv_head, all_config['result_csv_path'][-1])

        stage_num = self.global_arg['T'] // self.global_arg['Ts']
        for i in range(stage_num):
            Ti = i * self.global_arg['Ts'] + 1
            logging.info("stage %3d, Ti:%3d" % (i, Ti))
            self.main_env.T_clock = Ti
            # 每个stage遍历一遍当前模型，获取分布信息
            up_info['nkinfo'] = self.main_env.getModelDistri()
            logging.debug("max_value:{max}".format(**up_info['nkinfo']))
            # 运行一个Stage，Ti表示每个Stage的第一帧
            self.run_stage(Ti, up_info)


if __name__ == '__main__':
    import time
    import os

    # 准备工作，初始化实验环境，生成实验结果文件夹等
    all_config.load()
    moniter.LogInit()
    logging.info("Start")
    global_arg = arg.init_global_arg()
    env_arg = arg.init_env_arg(global_arg)
    exp_id = "_".join([
        "mul_agent_view",
        time.strftime("%Y%m%d-%H%M%S"),
        "N" + str(env_arg['N']),
        "K" + str(env_arg['K']),
        "P" + str(env_arg['P']),
        "T" + str(global_arg['T']),
        "Ts" + str(global_arg['Ts'])
    ])
    try:
        os.mkdir(os.path.join("result", exp_id))
    except:
        pass
    all_config['result_csv_path'] = [
        os.path.join("result", exp_id, "res_%s_%02d.csv" % (exp_id, i)) for i in range(global_arg["Nagent"])
    ]
    all_config['result_csv_path'].append(
        os.path.join("result", exp_id, "res_%s_overview.csv" % (exp_id))
    )
    all_config['network_csv_path'] = os.path.join("result", exp_id, "network.csv")
    main_control = MulControl()
    main_control.run_exp()  # 开始运行实验
