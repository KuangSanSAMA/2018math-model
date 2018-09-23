from CNC import CNC
from RGV import RGV
from util import *
import copy
class TaskSys:
    def __init__(self, group, task_type, mode='FIFO', cncs_type='00000000', fault=False, print_info=False):
        '''
            group: cnc机器类型组别
            task_type: 1/2，1表示一道工序模式，2表示两道工序模式。
            cncs_type: 八位二进制0/1字符串，0表示处理第一道工序，1表示处理第二道工序。
        '''
        self.group = group
        self.group_1 = [20, 33, 46, 560, 400, 378, 28, 31, 25]
        self.group_2 = [23, 41, 59, 580, 280, 500, 30, 35, 30]
        self.group_3 = [18, 32, 46, 545, 455, 182, 27, 32, 25]
        self.groups_para = [self.group_1, self.group_2, self.group_3]           # 各组cnc，rgv机器参数

        self.task_type = task_type          # 
        self.T = 8 * 60 * 60         # 一次加工总时间，单位：秒
        self.time = 0                # 计时器
        self.cnt = 0                 # 时间
        self.cncs_type = cncs_type
        if self.task_type == 1:
            self.cnc_ls = [CNC(i+1, group, self.task_type-1, self.groups_para, fault) for i in range(8)]         # task 1
        else:
            self.cnc_ls = [CNC(int(i)+1, group, int(cncs_type[i])+1, self.groups_para, fault) for i in range(8)]   # task 2
        self.rgv = RGV(0, group, self.task_type, self.groups_para)               # 初始化rgv

        self.wait_queue = []         # 任务等待队列，按照任务先后顺序
        self.wait_queue_task1 = []   # 第一阶段等待队列
        self.wait_queue_task2 = []   # 第二阶段等待队列
        self.wait_set = set()        # 任务等待集合
        self.wait_set_task1 = set()  # 第一阶段等待集合
        self.wait_set_task2 = set()  # 第二阶段等待集合
        self.mode = mode
        self.select_ls = []
        self.print_info = print_info
    
    def get_up_thres(self):
        if self.task_type == 1:
            return self.T/self.groups_para[self.group-1][3] * len(self.cnc_ls)
        n_0 = 0
        n_1 = 0
        for t in self.cncs_type:
            if t == '0':
                n_0 += 1
            if t == '1':
                n_1 += 1
        t_0 = self.groups_para[self.group-1][4]
        t_1 = self.groups_para[self.group-1][5]

        up_thres = self.T / max(t_0/n_0, t_1/n_0)
        return up_thres

    def stats(self, filename=None):
        # rgv
        num_result = self.rgv.get_result(self.T)                # 完成任务的数量 +
        if num_result != 0:
            mean_sys_do_task_time = self.T/num_result                   # 完成任务的平均时间 +
        else:
            mean_sys_do_task_time  = 0
        mean_cnc_do_task_time = mean_sys_do_task_time * len(self.cnc_ls)
        # cnc
        cnc_sum_wait_time = self.rgv.get_sum_wait_time(self.cnc_ls)     # cnc 完成所有任务的总等待时间 + 
        cnc_mean_wait_time = self.rgv.get_mean_wait_time(self.cnc_ls)   # cnc 每完成一个任务的平均等待时间  + 
        cnc_std_wait_time = self.rgv.get_std_wait_time(self.cnc_ls)     # cnc 完成每个任务的等待时间的标准差 +

        pre_cnc_wait_time = cnc_sum_wait_time/self.T    # cnc闲置占比 + 
        up_thres = self.get_up_thres()
        pre_task_in_up_thres = num_result / up_thres    #完成任务占上界的比

        return [num_result, mean_cnc_do_task_time, mean_sys_do_task_time, cnc_sum_wait_time, cnc_mean_wait_time, cnc_std_wait_time, pre_cnc_wait_time, pre_task_in_up_thres, up_thres]

    def write_stats_info(self):
        pass
    def print_stats(self):
        print('mode: %s, group: %d'%(self.mode, self.group))
        if self.cncs_type != None:
            print('cncs_type: %s'%self.cncs_type)
        rgv_sum = self.rgv.idle_time + self.rgv.move_time + self.rgv.updown_time + self.rgv.wash_time
        print('rgv, idle:%d, move:%d, updown:%d, wash:%d, sum:%d '%(self.rgv.idle_time, self.rgv.move_time, self.rgv.updown_time, self.rgv.wash_time, rgv_sum))
        print('mv_dist:', self.rgv.sum_move_distance)
        for i,cnc in enumerate(self.cnc_ls):
            cnc.stats()
            print('cnc_type: %d cnc: %d, wc_t: %d, idle_t: %d, mean_wt: %s'%(cnc.get_type(), i+1, cnc.wait_call_time, cnc.idle_time, str(cnc.mean_wait_time)) )
        # print(self.select_ls)

    def run(self):
        self.cnt = self.T
        while True:
            self.time = self.T - self.cnt
            self.update_cnn_condition(self.time)
            self.update_rgv_condition(self.time)
            self.cnt -= 1
            if self.cnt == 0:
                break
        if self.print_info:
            self.print_stats()
        self.stats()

    def update_cnn_condition(self, time):
        for cnc in self.cnc_ls:
            # 处于等待响应队列的cnc设备,0:初始化状态；2:完成任务状态
            status = cnc.get_status()
            if status == 0 or status == 2: 
                num = cnc.get_num()
                if num not in self.wait_set:
                    self.wait_queue.append(num)
                    self.wait_set.add(num)
                    # 如果cnc加工的是第一道工序
                    if cnc.type == 1:
                        self.wait_queue_task1.append(num)
                        self.wait_set_task1.add(num)
                    # 如果cnc加工的是第二道工序
                    if cnc.type == 2:
                        self.wait_queue_task2.append(num)
                        self.wait_set_task2.add(num)
                cnc.wait_call()

            # 处于加工状态的cnc设备
            if status == 1:
                cnc.do_task(time)
                # 检查任务是否已经完成，完成则添加到等待队列中
                if cnc.get_status() == 2:
                    num = cnc.get_num()
                    if num not in self.wait_set:
                        self.wait_queue.append(num)
                        self.wait_set.add(num)
                        # 如果cnc加工的是第一道工序
                        if cnc.type == 1:
                            self.wait_queue_task1.append(num)
                            self.wait_set_task1.add(num)
                        # 如果cnc加工的是第二道工序
                        if cnc.type == 2:
                            self.wait_queue_task2.append(num)
                            self.wait_set_task2.add(num)

            # 处于被rgv响应的设备，但是还没有开始任务
            if status == 3:
                cnc.idle()

            # 设备处于故障状态
            if status == -1:
                cnc.start_maintain(time)
            
            if status == 4:
                cnc.maintain(time)
    
    def update_rgv_condition(self, time):
        status = self.rgv.get_status()
        task_time = self.rgv.get_task_time()
        # rgv 处于闲置状态
        if status == 0:
            # 检查是否有cnc发出请求 或者 使用的是STSPW算法
            if self.wait_queue != [] or self.mode == 'STSPW':
                wait_queue_ls = [self.wait_queue, self.wait_queue_task1, self.wait_queue_task2]
                wait_set_ls = [self.wait_set, self.wait_set_task1, self.wait_set_task2]
                # 寻找目标
                k = self.rgv.update_status_move(wait_queue_ls, wait_set_ls, self.cnc_ls, self.mode, time)
                
                if k == -1:
                    self.rgv.idle()
                else:
                    self.select_ls.append(k)
                    # 如果cnc发出了响应请求，则通知cnc.num = k , 请求已被响应，并且整理等待队列信息
                    cnc_status = self.cnc_ls[k-1].get_status()
                    if cnc_status == 2 or cnc_status == 0:
                        self.cnc_ls[k-1].reply()
                        if k in self.wait_set:
                            self.wait_queue.remove(k)
                            self.wait_set.remove(k)
                            if self.task_type == 2:
                                if k in self.wait_set_task1:
                                    self.wait_queue_task1.remove(k)
                                    self.wait_set_task1.remove(k)
                                else:
                                    self.wait_queue_task2.remove(k)
                                    self.wait_set_task2.remove(k)
            else:
                self.rgv.idle()
        
        # rgv 处于移动状态
        elif status == 1:
            if task_time == 0:
                self.rgv.update_status_updown_material(self.cnc_ls, time)
            else:
                self.rgv.move()
        
        # rgv 处于上下料状态
        elif status == 2:
            if task_time == 0:
                # self.rgv.change_hand_status(self.rgv.num_sever_cnc, self.cnc_ls)
                self.cnc_ls[self.rgv.num_sever_cnc-1].start_task(time)
                # 如果两只机械手上存在3（两道加工后的料）
                if self.rgv.get_hand_1()[0] == 3 or self.rgv.get_hand_2()[0] == 3:
                    self.rgv.update_status_wash_material()
                else:
                    # 两种情况，一种取到一道加工后的料2，一种，什么也没取到
                    self.rgv.set_status(0)
                    self.update_rgv_condition(time)
            else:
                self.rgv.updown_material()
        
        # rgv 处于清洗材料状态
        elif status == 3:
            if task_time == 0:
                # 释放手上的成料
                self.rgv.release_hand()
                self.rgv.update_status_idle()
            else:
                self.rgv.wash_material()

            # 考虑边界
            status = self.rgv.get_status()
            if status == 0:
              self.update_rgv_condition(time)

    def save_stats_result(self):
        pass
    def output_result_task1(self):
        return self.rgv.get_result(self.T)

    def get_result_task1(self):
        return self.rgv.get_result_ls_task1(self.T)
    
    def get_result_task2(self):
        return self.rgv.get_result_ls_task2(self.T)
    
    def get_use_material_result_ls(self):
        return self.rgv.get_used_material_ls(self.T)

    def output_result_task2(self):
        return self.rgv.get_result(self.T)

class SearchPara:
    def __init__(self):
        self.group_ls = [1,2,3]
        self.task_type_ls = [1,2]
        self.mode_ls = ['FIFO', 'HRN', 'SPW', 'STSPW', 'BSTSPW']
        self.fault = [True, False]
        self.cncs_type_ls = []
        for i in range(1,255):
            self.cncs_type_ls.append(convert2binaryStr(i))
    
    def solve_task1(self, fault):
        result = []
        task_type = 1
        for group in self.group_ls:
            best_group_result = 0
            best_info = []
            for mode in self.mode_ls:
                sys = TaskSys(group=group, task_type=1, mode=mode, fault=fault)
                sys.run()
                # 完成的数量
                num_result = sys.output_result_task1()
                group_result = sys.get_use_material_result_ls()
                num_material = len(group_result)
                if num_result > best_group_result:
                    best_group_result = num_result
                    # group, task_type, mode, cncs_type, num_result
                    best_info = [[group, task_type, mode, num_result, num_material]] + group_result

            result.append(best_info)
            self.write_result_task1(best_info, fault)

    def solve_task2_for_table_mode(self, fault=False):
        task_type = 2
        repeat = 1
        if fault == True:
            repeat = 10
        best_cnc_type = self.get_task2_best_cnc_type()
        #print(self.mode_ls)
        for i, mode in enumerate(self.mode_ls, 0):
            mode_result = []
            index = copy.copy(i)
            for group in self.group_ls:
                # print(self.mode_ls)
                # print(best_cnc_type)
                # print(group)
                # print(index)
                cnc_type_ls = best_cnc_type[group-1][index]
                # print(mode, group, len(cnc_type_ls))
                for cnc_type in cnc_type_ls:
                    info = []
                    stats_result_ls = []
                    for i in range(repeat):
                        sys = TaskSys(group=group, task_type=task_type, cncs_type=cnc_type, mode=mode, fault=fault)
                        sys.run()
                        stats_result = sys.stats()
                        stats_result_ls.append(stats_result)

                    mean_stats_result = self.calcu_stats_mean(stats_result_ls)
                    info.append(cnc_type)
                    info.append(group)
                    info = info + mean_stats_result

                    #方法mode_i在组group中使用cnc_type的结果
                    mode_result.append(info)

            filename = 'task_' + str(task_type) + '_mode_' + mode + '.txt'
            self.write_task2_table(filename, mode_result, way='group', fault=fault)

    def solve_task2_for_table_group(self, fault=False):
        task_type = 2
        best_cnc_type = self.get_task2_best_cnc_type()
        repeat = 1
        if fault == True:
            repeat = 10
        for group in self.group_ls:
            group_result = []
            for i,mode in enumerate(self.mode_ls):
                cnc_type_ls = best_cnc_type[group-1][i]
                for cnc_type in cnc_type_ls:
                    info = []
                    stats_result_ls = []
                    for _ in range(repeat):
                        sys = TaskSys(group=group, task_type=task_type, cncs_type=cnc_type, mode=mode, fault=fault)
                        sys.run()
                        stats_result = sys.stats()
                        stats_result_ls.append(stats_result)
                    
                    mean_stats_result = self.calcu_stats_mean(stats_result_ls)

                    info.append(cnc_type)
                    info.append(mode)
                    info = info + mean_stats_result

                    #方法mode_i在组group中使用cnc_type的结果
                    group_result.append(info)

            filename = 'task_' + str(task_type) + '_group_' + str(group) + '.txt'
            self.write_task2_table(filename, group_result, way='mode', fault=fault)
    
    def write_task2_table(self, filename, result, way, fault):
        path = 'result/'
        if fault == True:
            path = path + 'fault/'
        path = path + 'task2/table/'

        with open(path+way+'/'+filename, 'w') as f:
            for re in result:
                for tmp in re:
                    f.write(str(tmp) + '\t')
                f.write('\n')
            f.close()
    
    def calcu_stats_mean(self, stats_result_ls):
        if len(stats_result_ls) == 1:
            return stats_result_ls[0]
        else:
            tmp_ls = [0 for i in range(len(stats_result_ls[0]))]
            for stats_result in stats_result_ls:
                for i in range(len(stats_result)):
                    tmp_ls[i] += stats_result[i]
            
            for i in range(len(tmp_ls)):
                tmp_ls[i] = tmp_ls[i]/len(stats_result_ls)
            return tmp_ls

    def solve_task1_for_table_mode(self, fault=False):
        task_type = 1
        repeat = 1
        if fault == True:
            repeat = 10
        for mode in self.mode_ls:
            mode_result = []
            for group in self.group_ls:
                stats_result_ls = []
                for _ in range(repeat):
                    sys = TaskSys(group=group, task_type=task_type, mode=mode, fault=fault)
                    sys.run()
                    stats_result = sys.stats()
                    stats_result_ls.append(stats_result)
                
                mean_stats_result = self.calcu_stats_mean(stats_result_ls)

                info = ['group' + str(group)] + mean_stats_result

                # group_result = sys.output_result_task1()
                mode_result.append(info)

            filename = 'task_' + str(task_type) + '_mode_' + mode + '.txt'
            self.write_task1_table(filename, mode_result, way='group', fault=fault)
    
    def solve_task1_for_table_group(self, fault=False):
        task_type = 1
        repeat = 1
        if fault == True:
            repeat = 10
        for group in self.group_ls:
            group_result = []
            for mode in self.mode_ls:
                stats_result_ls = []
                for _ in range(repeat):
                    sys = TaskSys(group=group, task_type=task_type, mode=mode, fault=fault)
                    sys.run()
                    stats_result = sys.stats()
                    stats_result_ls.append(stats_result)

                mean_stats_result = self.calcu_stats_mean(stats_result_ls)

                info = [mode] + mean_stats_result
                group_result.append(info)
            
            filename = 'task_' + str(task_type) + '_group_' + str(group) + '.txt'
            self.write_task1_table(filename, group_result, way='mode', fault=fault)
    
    def write_task1_table(self, filename, result, way, print_title=False, fault=False):
        if print_title:
            title = [way, 'num_result', 'cnc_do_task_time', 'sys_do_task_time', 'cncs_sum_wait_time', 'cnc_mean_wait_time', 'cnc_std_wait_time', 'pre_cnc_idle', 'pre_sys_do_task', 'up_thred']
        path = 'result/'
        if fault == True:
            path = path + 'fault/'
        path = path + 'task1/table/'

        with open(path+way+'/'+filename, 'w') as f:
            if print_title:
                for t in title:
                    f.write(t)
                    f.write('\t')
                f.write('\n')
            for re in result:
                for i,tmp in enumerate(re):
                    if i == 0 and print_title == False:
                        continue
                    f.write(str(tmp) + '\t')
                f.write('\n')
            f.close()

    def find_best_cnc_result(self, exist=1):
        if exist == 1:
            best_cnc_type_result = self.get_task2_best_cnc_type()
            return best_cnc_type_result
            
        best_num_result = self.get_task2_best_num_result()
        task_type = 2
        best_cnc_type_result = []
        for group in self.group_ls:
            # 寻找每组中，每个方法，最大的num_result
            best_cnc_type_group = []

            for i, mode in enumerate(self.mode_ls):
                best_num_result_mode = best_num_result[group-1][i]
                best_cnc_type_ls = []
                # 寻找group中使用mode方法的最大num_result

                for cncs_type in self.cncs_type_ls:
                    sys = TaskSys(group=group, task_type=task_type, mode=mode,
                                  cncs_type=cncs_type, fault=False, print_info=False)
                    sys.run()
                    num_result = sys.output_result_task2()
                    if num_result == best_num_result_mode:
                        best_cnc_type_ls.append(cncs_type)
                
                best_cnc_type_group.append(best_cnc_type_ls)
            
            filename = 'task_2'+ '_group_' + str(group) + '_best_cnc_type' + '.txt'

            with open('para/'+filename, 'w') as f:
                for best_cnc_type_mode in best_cnc_type_group:
                    for best_cnc_type in best_cnc_type_mode:
                        f.write(str(best_cnc_type) + '\t')
                    f.write('\n')
                f.close()

            best_cnc_type_result.append(best_cnc_type_group)

        return best_cnc_type_result
    
    def get_task2_best_cnc_type(self):
        best_cnc_type_group = []
        for group in self.group_ls:
            best_cnc_type_mode = []
            with open('para/'+'task_2_group_'+ str(group) +'_best_cnc_type.txt', 'r') as f:
                lines = f.readlines()
                for line in lines:
                    line = [r for r in line.split('\n')]
                    line = line[0].split('\t')
                    for l in line:
                        if l == '':
                            line.remove(l)
                    best_cnc_type_mode.append(line)
                f.close()

            best_cnc_type_group.append(best_cnc_type_mode)
        return best_cnc_type_group
    
    def get_task2_best_num_result(self):
        best_num_result = []
        with open('task2_best_num_result.txt', 'r') as f:
            lines = f.readlines()
            for line in lines:
                line = line.split('\t')
                line = [l.strip('\n') for l in line]
                for l in line:
                    if l == '':
                        line.remove(l)
                best_num_result_group = [int(r) for r in line]
                best_num_result.append(best_num_result_group)
            f.close()
        return best_num_result

    def find_best_num_result(self, exist=1):
        if exist == 1:
            return self.get_task2_best_num_result()

        task_type = 2
        best_num_result = []
        for group in self.group_ls:
            # 寻找每组中，每个方法，最大的num_result
            best_num_result_group = []

            for mode in self.mode_ls:
                best_num_result_mode = 0

                # 寻找group中使用mode方法的最大num_result

                for cncs_type in self.cncs_type_ls:
                    sys = TaskSys(group=group, task_type=task_type, mode=mode, cncs_type=cncs_type,fault=False, print_info=False)
                    sys.run()
                    num_result = sys.output_result_task2()
                    if num_result > best_num_result_mode:
                        best_num_result_mode = num_result
                
                best_num_result_group.append(best_num_result_mode)
            best_num_result.append(best_num_result_group)

        with open('task2_best_num_result.txt', 'w') as f:
            for num_result_group in best_num_result:
                for num_result_mode in num_result_group:
                    f.write(str(num_result_mode) + '\t')
                f.write('\n')
            f.close()

        return best_num_result
        
    def solve_task2(self, fault):
        result = []
        task_type = 2
        best_cncs_type = self.get_task2_best_cnc_type()
        for group in self.group_ls:
            best_group_result = 0
            best_info = []

            for i, mode in enumerate(self.mode_ls):
                best_cnc_result_in_mode = 0
                best_cnc_info = []
                self.cncs_type_ls = best_cncs_type[group-1][i]

                for cncs_type in self.cncs_type_ls:
                    sys = TaskSys(group=group, task_type=task_type, mode=mode, cncs_type=cncs_type,fault=fault, print_info=False)
                    sys.run()
                    num_result = sys.output_result_task2()
                    cncs_result = sys.get_use_material_result_ls()
                    num_material = len(cncs_result)
                    if num_result > best_cnc_result_in_mode:
                        best_cnc_result_in_mode = num_result
                        best_cnc_info = [[group, task_type, mode, cncs_type, num_result, num_material]] + cncs_result
                    
                    print(group, task_type, mode, cncs_type, num_result)

                mode_result = best_cnc_result_in_mode
                mode_info = best_cnc_info

                if mode_result > best_group_result:
                    best_group_result = mode_result
                    best_info = mode_info
            
            result.append(best_info)
            self.write_result_task2(best_info, fault)

    def write_result_task1(self, result, fault):
        filename = 'group_' + str(result[0][0]) + '_task_' + str(result[0][1]) + '_mode_' + str(result[0][2]) + '_num_worked_' + str(result[0][3]) + '-' + str(result[0][4])
        path = 'result/'
        if fault == True:
            path = path + 'fault/'
        path = path + 'task1/'
        print(path + filename )
        with open(path + filename+'.txt','w') as f:
            for i in range(1,len(result)):
                f.write(str(result[i][0])+'\t'+str(result[i][1])+'\t'+str(result[i][2])+'\t'+str(result[i][3])+'\n')
            f.close()
    
    def write_result_task2(self, result, fault):
        filename = 'group_' + str(result[0][0]) + '_task_' + str(result[0][1]) + '_mode_' + str(result[0][2]) + '_cncs_type_'+str(result[0][3])+'_num_worked_' + str(result[0][4]) + '-' + str(result[0][5])
        path = 'result/'
        if fault == True:
            path = path + 'fault/'
        path = path + 'task2/'
        with open(path+filename+'.txt','w') as f:
            for i in range(1,len(result)):
                f.write(str(result[i][0])+'\t'+str(result[i][1])+'\t'+str(result[i][2])+'\t'+str(result[i][3])+'\t'+str(result[i][4])+'\t'+str(result[i][5])+'\t'+str(result[i][6])+'\n')
            f.close()
    
    def status_cncs_type(self):
        task_type = 2
        for group in self.group_ls:

            for mode in self.mode_ls:
                num_type_ls = []
                cncs_type_ls = []
                cncs_result_ls = []

                for i, cncs_type in enumerate(self.cncs_type_ls):
                    sys = TaskSys(group=group, task_type=task_type, mode=mode, cncs_type=cncs_type,fault=False, print_info=False)
                    sys.run()
                    cncs_result = sys.output_result_task2()
                    
                    num_type_ls.append(i+1)
                    cncs_type_ls.append(cncs_type)
                    cncs_result_ls.append(cncs_result)

                    print(group, task_type, mode, i+1, cncs_type, cncs_result)

                self.write_cncs_type(group, task_type, mode, num_type_ls, cncs_type_ls, cncs_result_ls)
    
    def write_cncs_type(self, group, task_type, mode, num_type_ls, cncs_type_ls, cncs_result_ls):
        filename = 'group_' + str(group) + '_task_type_' + str(task_type) + '_mode_' + str(mode) + '.txt'
        with open('result/hist/'+filename, 'w') as f:
            for i in range(len(cncs_type_ls)):
                f.write(str(num_type_ls[i]) + '\t' + str(cncs_type_ls[i]) + '\t' + str(cncs_result_ls[i]) + '\n')
            f.close()
    

if __name__ == '__main__':
    # sys = TaskSys(group=2, task_type=1, mode='STSPW', cncs_type='10010101',fault=True, print_info=False)
    # sys.run()
    # num_result = sys.output_result_task2()
    # print(num_result)
    # print(num_result)
    SP = SearchPara()
    # SP.solve_task1()
    # SP.solve_task2()
    # SP.status_cncs_type()

    # SP.solve_task1_for_table_mode()
    # SP.solve_task1_for_table_group()

    # SP.find_best_num_result(exist=0)
    # SP.find_best_cnc_result(exist=0)

    # SP.solve_task2_for_table_mode()
    # SP.solve_task2_for_table_group()

    # SP.solve_task1(fault=True)
    # SP.solve_task2(fault=True)

    # SP.solve_task1_for_table_mode(fault=True)
    # SP.solve_task1_for_table_group(fault=True)

    SP.solve_task2_for_table_mode(fault=True)
    SP.solve_task2_for_table_group(fault=True)
