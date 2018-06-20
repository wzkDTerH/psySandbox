# -*- coding:utf-8 -*-
import os
from random import normalvariate as Norm
from random import uniform
from math import exp, pow, tanh, cos, pi
from copy import deepcopy
import logging
from util.util import max_choice, random_choice, softmaxM1, clip, clip_rsmp, clip_tanh
from env import Area


def init_global_arg():
    arg = {
        'T': 128,  # 模拟总时间
        "Ts": 16,  # 每个stage的帧数
        "Nagent": 10,  # Agent数量
        'D_env': False,  # 动态地形开关
        'mul_agent': False   # 多人互动开关
    }
    return arg


def init_env_arg(global_arg):
    # NK model
    arg = {
        'N': 6,
        'K': 2,
        'P': 4,  # 每个位点状态by Cid
        'T': global_arg['T'],  # 模拟总时间
        'Tp': global_arg['T'],  # 每个地形持续时间/地形变化耗时 by Cid
        'dynamic': global_arg['D_env']  # 动态地形开关
    }

    # 环境情景模型模块
    arg['ESM'] = {
        "f-req": 0.75,  # 适应要求，及格线
        "p-cplx": 1 - 0.75 / (1 + exp(arg['K'] - 5)),
        # (lambda Tp: 1 - 0.75 ** (1.0 * global_arg['T'] / Tp) / (1 + exp(arg['K'] - 5))),

        "p-ugt": (1 - tanh(0.1 * (global_arg['Ts'] - 32))) * 0.5
    }

    # 区域相关参数，代表目标
    arg['area'] = {
        "sample_num": 100,  # 抽样个数
        "max_dist": 3,  # 游走距离
        "mask_num": min(5, arg['N'])  # 可移动的位点限制
    }

    plan_a = 0.1  # 距离对计划得分影响系数
    arg['plan'] = {
        # 计划得分
        'eval': (lambda dist, trgt: trgt * (1 - plan_a * (1 - trgt)) ** dist)
    }

    # 个体可以采取的各项行动，行动本身的参数
    arg['ACT'] = {
        # 行动执行相关参数表
        'zyzx': {
            # zyzx自由执行相关参数
        },
        'xdzx': {
            # 执行计划的概率
            'do_plan_p': (
                lambda st_val, dist, trgt: 0.5 + 0.5 * tanh(50 * (arg['plan']['eval'](dist, trgt) - st_val))),
            'kT0': 0.01,  # default 0.5
            'cool_down': 0.995,  # default 0.99
        },
        # 获取信息相关参数表
        'hqxx': {
            "mask_n": 2,  # 区域的方向夹角大小，指区域内的点中允许变化的位点数量
            "dist": 3,  # 区域半径，所有点和中心点的最大距离
            "dfs_p": 0.5,  # 表示多大概率往深了走
            "sample_n": 50  # 从区域中抽样的数量
        },
        # 计划拟定相关参数表
        'jhnd': {
            "sample_num": 30,
            "dfs_r": 0.5
        },
        # 计划决策相关参数表
        'jhjc': {
            "plan_eval": arg['plan']['eval']
        },
        "whlj": {
            "k": global_arg['Nagent'] // 2,
            "delta_relate": lambda old: 0.1 * (1 - old)  # 0.1是改变速率，可以手动修改
        },
        "dyjs": {
            "delta_relate": lambda old: 0.1 * (1 - old)  # 0.1是改变速率，可以手动修改
        }
    }

    # 集体行动相关参数表
    arg['meeting'] = {
        'xxjl': {
            'last_p_t': 32,  # 最近多少帧内的信息
            'max_num': 3  # 最多共享多少个
        }
    }
    return arg


# 社会网络相关参数
def init_soclnet_arg(global_arg, env_arg):
    arg = {}
    arg['Nagent'] = global_arg['Nagent']

    # 权重到距离的转化公式
    # networkx自带的Cc算法是归一化的,若令 dist=1.01-x上述距离定义的最短距为0.01，因此最短距不是(g-1)而是0.01*(g-1)
    arg['pow_w2d'] = (lambda x: 1 / (0.01 + x) + 0.01)

    arg['re_decr_r'] = 0.98  # 自然衰减率

    return arg


def init_agent_arg(global_arg, env_arg):
    arg = {}
    # 个体属性差异
    arg['a'] = {
        "insight": clip_rsmp(0.001, 0.999, Norm, mu=0.5, sigma=0.2),  # 环境感知能力
        "act": Norm(0.5, 0.1),  # 行动意愿
        "xplr": Norm(0.5, 0.3),  # 探索倾向
        "xplt": Norm(0.5, 0.3),  # 利用倾向
        "enable": Norm(0.5, 0.1),
        "rmb": 64
    }

    # 适应分数观察值的偏差
    ob_a = 0.01  # default 0.025
    arg["ob"] = (lambda x: Norm(x, ob_a / arg['a']['insight']))  # default公式，
    #    arg["ob"] = (lambda x: Norm(x, 0.05))  #测试公式

    incr_rate = 0.03  # 关系增加速率
    arg["re_incr_g"] = (
        lambda old_re: (1 - 2 * incr_rate) * old_re + 2 * incr_rate)  # 表示general的increase，在参加完任意一次集体活动后被调用

    arg['dP_r'] = {
        "other": 0.2,  # 对他人给的计划变化幅度更大
        "self": 0.1  # 对自己的计划变化幅度较小（效能提升小）
    }
    dP_s = 100  # 对变化的敏感度
    arg["dPower"] = (lambda dF, dP_r: dP_r * tanh(dP_s * dF))

    arg["pwr_updt_g"] = (lambda old_pwr, dP: (1 - abs(dP)) * old_pwr + 0.5 * (dP + abs(dP)))
    arg["d_pwr_updt_g"] = (lambda old_pwr, dP: arg["pwr_updt_g"](old_pwr, dP) - old_pwr)

    arg['default'] = {
        "stage": {},  # 各种第0个stage的参数放在这里
        "frame": {  # 各种第0帧的参数放在这里
            # 主观情景模型
            "PSM": {
                "m-info": [],  # 新内容，存储各种临时信息
                "m-plan": [],
                "a-plan": None,
                'a-need': 0,  # 行动需求，原来的f-need
                's-sc': 0
            },
            # 行动偏好参数
            'ACT': {
                'p': {
                    'xdzx': 1,  # 行动执行
                    'hqxx': 0,  # 获取信息
                    'jhnd': 0  # 计划拟定
                }
            }
        }
    }
    return arg


def init_group_arg(global_arg, env_arg, T):
    arg = {}
    return arg


def init_stage_arg(global_arg, env_arg, agent_arg, last_arg, T):
    return {}


# 每帧刷新的参数列表
def init_frame_arg(global_arg, env_arg, agent_arg, stage_arg, last_arg, Tp, PSMfi):
    arg = {}

    arg['PSM'] = {
        "f-req": Norm(env_arg['ESM']['f-req'], 0.01 / agent_arg['a']['insight']),
        "p-cplx": Norm(env_arg['ESM']['p-cplx'], 0.01 / agent_arg['a']['insight']),  # 只是初始值这样获得
        "p-ugt": Norm(env_arg['ESM']['p-ugt'], 0.01 / agent_arg['a']['insight']),  # 只是初始值这样获得
        "m-info": deepcopy(last_arg['PSM']['m-info']),  # 新版用法不一样
        "m-plan": deepcopy(last_arg['PSM']['m-plan']),  # 新版用法不一样
        "a-plan": deepcopy(last_arg['PSM']['a-plan']),  # 拍死他丫的
        "s-sc": deepcopy(last_arg['PSM']['s-sc'])  # 新版用法不一样
    }

    # 计算当前个体在这一帧感知到的行动需求
    # PSManeed_r = 1.0 / (1 + exp(5 * (PSMfi / arg['PSM']['f-req'] - 1)))
    # PSManeed_a = 0.5
    # arg['PSM']['a-need'] = PSManeed_a * last_arg['PSM']['a-need'] + (1 - PSManeed_a) * PSManeed_r

    # 判断当前个体在这一帧是否采取行动
    # f1 = 1 + 0.5 * tanh(5 * (arg['PSM']['a-need'] - 0.75)) \
    #    + 0.5 * tanh(5 * (agent_arg['a']['act'] - 0.5))
    # g1 = 1 - 0.2 * tanh(5 * (arg['PSM']['p-cplx'] - 0.625))
    # h1 = 1 + 0.1 * cos(pi * (arg['PSM']['p-ugt'] - 0.5))
    # arg['PROC'] = {
    #    'a-m': f1 * g1 * h1,  # 行动动机，代表行动意愿的强度
    #    'a-th': 0  # 行动阈值，初始0.6，测试版保证行动
    # }
    arg['PROC'] = {}
    arg['PROC']['action'] = True  # 目前始终行动
    # arg['PROC']['action'] = (Norm(arg['PROC']['a-m'] - arg['PROC']['a-th'], 0.1) > 0)  # TRUE行动，FALSE不行动

    # 行动执行的偏好分(1-3), default = 2
    xdzx_c = 2  # 行动执行偏好常数
    xxhq_c = 0
    jhjc_c = 0
    whlj_c = 0
    dyjs_c = 0
    tjzt_c = 0
    odds_base = 1
    xdzx_r = 1  # 行动执行随dF变化的最大幅度
    jhjc_r = 0.5  # 计划决策随dF变化的最大幅度
    arg['ACT'] = {
        'odds': {
            "xdzx": lambda dF: xdzx_c + odds_base * (1 + xdzx_r * tanh(100 * dF)),
            "hqxx": lambda dF: xxhq_c + odds_base * (0.5 + agent_arg['a']['xplr']),
            "jhjc": lambda dF: jhjc_c + odds_base * (0.5 + agent_arg['a']['xplt']) * (1 + jhjc_r * tanh(100 * dF)),
            "whlj": lambda dF: whlj_c + odds_base * (0.5 + agent_arg['a']['enable']),
            "dyjs": lambda dF: dyjs_c + odds_base * (0.5 + agent_arg['a']['enable']),
            "tjzt": lambda dF: tjzt_c + odds_base * 0   # 先去掉这个选项
            # "tjzt": lambda dF: tjzt_c + odds_base * (0.5 + agent_arg['a']['enable'])
        },
        "p": {},
        "p-cmt": {},
        "p-req": {}
    }
    k_cmt = 0.2
    arg['ACT']['p-cmt']['xxjl'] = lambda max_relat, max_power, self_efficacy: \
        (1 - k_cmt) * max_relat ** 2 + k_cmt
    arg['ACT']['p-cmt']['tljc'] = lambda max_relat, max_power, self_efficacy: \
        (1 - max(0, max_power - self_efficacy)) * max_relat ** 2 + max(0, max_power - self_efficacy)
    arg['ACT']['p-cmt']['xtfg'] = lambda max_relat, max_power, self_efficacy: \
        (1 - max(0, max_power - self_efficacy)) * max_relat ** 2 + max(0, max_power - self_efficacy)
    k_req = 0.2
    arg['ACT']['p-req']['xxjl'] = lambda self_efficacy, host_Cc, host_Cod: \
        (1 - k_req) * host_Cc ** 2 + k_req
    arg['ACT']['p-req']['tljc'] = lambda self_efficacy, host_Cc, host_Cod: \
        (1 - self_efficacy) * host_Cod ** 2 + self_efficacy
    arg['ACT']['p-req']['xtfg'] = lambda self_efficacy, host_Cc, host_Cod: \
        (1 - self_efficacy) * host_Cod ** 2 + self_efficacy

    '''
    # 以下为老的代码部分
    # 以下参数用于确定采取何种行动的过程
    xdzx_a = 0.5
    arg['ACT']['p']['xdzx'] = xdzx_a * last_arg['ACT']['p']['xdzx'] + (1 - xdzx_a) * 0.5  # 行动执行的偏好是常数，为0.5

    hqxx_a = 0.5
    f2 = 1 - tanh(10 * (last_arg['PSM']['s-sc'] - 0.8 * arg['PSM']['f-req']))
    g2 = 1 + 0.2 * tanh(5 * (agent_arg['a']['xplr'] - 0.5))
    h2 = 1 + 0.1 * cos(pi * (arg['PSM']["p-ugt"] - 0.5))
    l2 = 1 + 0.2 * tanh(5 * (arg['PSM']['p-cplx'] - 0.5))
    arg['ACT']['p']['hqxx'] = hqxx_a * last_arg['ACT']['p']['hqxx'] + (1 - hqxx_a) * f2 * g2 * h2 * l2

    f3 = 1 + tanh(5 * (last_arg['PSM']['s-sc'] - 0.8 * arg['PSM']['f-req']))
    g3 = 1 + 0.2 * tanh(5 * (agent_arg['a']['xplt'] - 0.5))
    h3 = 2 + tanh(5 * (arg["PSM"]['p-ugt'] - 1))
    jhnd_a = 0.5
    arg['ACT']['p']['jhnd'] = jhnd_a * last_arg['ACT']['p']['jhnd'] + (1 - jhnd_a) * f3 * g3 * h3
    if (len(arg['PSM']['m-plan']) < 1):
        arg['ACT']['p']['jhnd'] = 0
    arg['ACT']['choice'] = random_choice(softmaxM1(arg['ACT']['p']))
    '''
    return arg
