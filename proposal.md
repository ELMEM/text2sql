# 实现方案

## Version 1.0

实现 thought_spot 类似的 (配合前端ui帮助，通过 query suggestion 的方式转换 text to sql) text-to-sql 

> 任务描述

- 输入
  
    1. 上次suggestion选择的末尾到当前的末尾的文本
    2. 用户当前输入的完整文本
    3. 之前已经选择的 field 或 value 或 op 等

- 输出：

    - 判断 "输入1" 是 "select column", "where column", "having column", "orderBy column", "select op", "where op", 
      "having op", "where condition", "where value", 还是 "having value"
    - 判断 "输入1" 是具体哪个 column，给排序分数
    - 将 "输入3" 以及 上面的两个输入 结合，构建 sql 语句

相关功能

  #### 1. 若 "输入1" 为 value 值 
    
        a. 以 table content 的 vector 判断是否为 value
        b. 识别 tok k columns
        c. 若 top1 与 top2 以后的拉开一定差距，可以直接取 top1
        d. 若 top1 与 topk 接近，则往前看 "输入2" "输入3"，根据前面的1-2个"输入3"进行联合识别或判断
  
    
  #### 2. 若 "输入1" 为 column 相关的描述

        a. 以 column description 的 vector 判断是否为 column 描述
        b. 识别 top k columns
        c. 判断 select 还是 where/having 还是 group by (根据周围的输入、或用户的选择)


  #### 3. 若 "输入1" 为 group by 的相关描述

        类同 ... 

  #### 4. 若 "输入1" 为 condition op (and or) 的相关描述

        类同 ...

  #### 5. 若 "输入1" 为 op (>, <, =, !=, in) 的相关描述

        a. 以 op description 的 vector 判断是否为 op 描述
        b. 识别 top1 op
        c. 根据 前后 "输入3" 判断 op 归属

  #### 6. 整合 "输入3" 以及  "输入1" 得出的结论，输入 sql 片段

        ...

> Version 2.0


