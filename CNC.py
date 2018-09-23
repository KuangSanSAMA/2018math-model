import numpy as np
import random
class CNC(object):
    def __init__(self, num, group, type, groups_para, fault=False):
        self.num = num          # 设备奇偶编号
        self.group = group      # {1, 2, 3}组
        self.type = type        # 0: 一道工序; 1:两道工序之第一道; 2:两道工序之第二道
        self.fault = fault
        self.err_pro = 0.01     # 故障的发生概率
        self.status = 0           # -1:故障; 0:闲置; 1:加工; 2:完成加工; 3:请求已被响应; 4:维修状态。
        self.need_time = 0      # 需要维修的时间, 单位为s, 符合正态分布，区间在[600, 1200]
        self.pos = (self.num - 1) // 2    # cnc所在位置
        self.time = groups_para[self.group-1][3]    # CNC加工完成一个一道工序的物料所需时间
        self.time_1 = groups_para[self.group-1][4]  # CNC加工完成一个两道工序物料的第一道工序所需时间
        self.time_2 = groups_para[self.group-1][5]  # CNC加工完成一个两道工序物料的第二道工序所需时间

        self.time_mv1 = groups_para[self.group-1][0]  # RGV移动1个单位所需时间
        self.time_mv2 = groups_para[self.group-1][1]  # RGV移动2个单位所需时间
        self.time_mv3 = groups_para[self.group-1][2]  # RGV移动3个单位所需时间
        self.time_mv_ls = [self.time_mv1, self.time_mv2, self.time_mv3]

        self.time_odd = groups_para[self.group-1][6] # RGV为CNC1#，3#，5#，7#一次上下料所需时间
        self.time_eve = groups_para[self.group-1][7] # RGV为CNC2#，4#，6#，8#一次上下料所需时间

        self.wait_call_time = 0  # cnc等待响应时间
        self.idle_time = 0  # cnc闲置时间
        self.wait_time = 0  # cnc结束上一个任务，等待下次任务所花费的时间
        self.wait_time_ls = []
        self.mean_wait_time = 0
        self.std_wait_time = 0  
        self.maintain_time = 0
        self.task_time = 0      # 任务计时器
        self.response_ratio = 0 # 响应比

        self.container = [0, -1]    #(0, 编号) 0，空；1，生料；2，一次加工后；3，熟料
        
        self.max_dist = 100000
        self.result_ls = []     # cnc.num, start_time, end_time
        self.last_updown_time = -1
        
    def get_response_ratio(self, rgv_mv_time, rgv_updown_time):
        self.response_ratio = self.wait_time/(rgv_mv_time + rgv_updown_time)
        return self.response_ratio
    
    def get_pos(self):
        return self.pos

    # 请求被响应
    def reply(self):
        self.status = 3

    # 初始化cnn任务
    def start_task(self, time):
        # 将cnn置为加工状态
        self.status = 1
        # 任务开始，记录上/下料开始时间 = 上/下料结束时间 - 上/下料花费时间
        if self.num % 2 == 0:
            now_updown_time = time - self.time_eve
        else:
            now_updown_time = time - self.time_odd

        if self.last_updown_time != -1:
            self.result_ls.append([self.num, self.last_updown_time, now_updown_time])

        self.last_updown_time = now_updown_time
        # 初始化任务时间，取决于cnc机器工作类型
        if self.type == 0:
            self.task_time = self.time
        elif self.type == 1:
            self.task_time = self.time_1
        elif self.type == 2:
            self.task_time = self.time_2

        # self.do_task(time)

    # cnc执行任务，结束返回1
    def do_task(self, time):
        self.task_time -= 1
        if self.task_time == 0:
            self.container[0] = self.container[0]+1
            # 任务完成，更新cnc状态，表示请求rgv处理，分配任务
            self.status = 2
            self.wait_time_ls.append(self.wait_time)
            self.wait_time = 0
        
        else:
            if self.status == 1 and self.fault==True:
                r = random.random()
                self.update_err_pro()
                if r < self.err_pro:
                    self.status = -1
    # cnc闲置状态
    def idle(self):
        self.wait_time += 1
        self.idle_time += 1
    
    # cnc等待响应状态
    def wait_call(self):
        self.wait_call_time += 1
        self.idle()
    
    def start_maintain(self, time):
        # 将cnn置为维修状态
        self.status = 4
        # 初始化本次维修时间，维修时间服从正态分布
        self.task_time = self.get_maintain_time()
        self.maintain(time)

    def get_maintain_time(self, min_t=10*60, max_t=20*60):
        return random.randint(min_t, max_t)

    def maintain(self, time):
        self.task_time -= 1
        self.maintain_time += 1
        # 检查维修是否结束
        if self.task_time == 0:
            # cnc设置为初始化状态
            self.status = 0
            self.wait_time = 0
            # cnc废料清空
            self.container = [0, -1]
    
    def reset_wait_time(self):
        self.wait_time = 0

    def get_status(self):
        # 不处于加工状态 | 关闭故障模拟
        # if self.status != 2 or self.fault == False:
        #     return self.status
        # r = random.random()
        # if r < self.err_pro:
        #     self.status = -1
        return self.status

    def get_num(self):
        return self.num
    
    def get_wait_time(self):
        return self.wait_time
    
    def stats(self):
        if self.wait_time_ls != []:
            self.mean_wait_time = np.mean(self.wait_time_ls)
    
    def get_dist_time(self):
        if self.task_time == self.time_mv_ls[0]:
            return 1
        if self.task_time == self.time_mv_ls[1]:
            return 2
        if self.task_time == self.time_mv_ls[2]:
            return 3
        if self.task_time == 0:
            return 0
        return self.max_dist
    
    def get_type(self):
        return self.type
    
    def update_err_pro(self):
        if self.type == 0:
            self.err_pro = 0.01/self.time
        elif self.type == 1:
            self.err_pro = 0.01/self.time_1
        elif self.type == 2:
            self.err_pro = 0.01/self.time_2
