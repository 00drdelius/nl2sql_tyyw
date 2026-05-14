-- 1. imoc_checkin_user 考勤人员打卡记录表
CREATE TABLE imoc_checkin_user (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    userid INT NOT NULL COMMENT '用户 ID',
    project_id INT NOT NULL COMMENT '项目 ID',
    duty_id INT NOT NULL COMMENT '排班 ID',
    class_id INT NOT NULL COMMENT '班次 ID',
    range_id INT NOT NULL COMMENT '时间段 ID',
    related_id INT NOT NULL COMMENT '关联 duty_user 的 ID',
    type VARCHAR(255) NOT NULL COMMENT '类型',
    range_start_time VARCHAR(255) NOT NULL COMMENT '考勤上班时间',
    range_end_time VARCHAR(255) NOT NULL COMMENT '考勤下班时间',
    tertian SMALLINT NOT NULL COMMENT '是否隔日',
    duty_date DATE NOT NULL COMMENT '值班日期',
    duty_location VARCHAR(255) NOT NULL COMMENT '值班打卡位置',
    location VARCHAR(255) NOT NULL COMMENT '实际打卡位置',
    lng VARCHAR(255) NOT NULL COMMENT '经纬度',
    lat VARCHAR(255) NOT NULL COMMENT '经纬度',
    status VARCHAR(255) NOT NULL COMMENT '状态',
    create_time DATETIME NOT NULL COMMENT '创建时间',
    update_time DATETIME NOT NULL COMMENT '更新时间',
    is_del SMALLINT NOT NULL COMMENT '是否删除',
    is_manual SMALLINT DEFAULT 0 COMMENT '是否手动签到'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤人员打卡记录表-记录人员的每一次打卡记录';

-- 2. imoc_class 考勤班次表
CREATE TABLE imoc_class (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    name VARCHAR(255) NOT NULL COMMENT '班次名称',
    endure_minutes VARCHAR(255) NOT NULL COMMENT '容忍时间',
    info VARCHAR(255) NOT NULL COMMENT '说明',
    create_time DATETIME NOT NULL COMMENT '创建时间',
    create_userid INT NOT NULL COMMENT '创建用户 ID',
    update_time DATETIME NOT NULL COMMENT '更新时间',
    update_userid INT NOT NULL COMMENT '更新用户 ID',
    is_del SMALLINT NOT NULL COMMENT '是否删除'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤班次表-配置考勤班次';

-- 3. imoc_class_duty 考勤排班表
CREATE TABLE imoc_class_duty (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    project_id INT NOT NULL COMMENT '项目 ID',
    class_id INT COMMENT '班次 ID',
    start_date DATE COMMENT '开始日期',
    end_date DATE COMMENT '结束日期',
    type VARCHAR(255) COMMENT '值班方式',
    remark VARCHAR(255) COMMENT '备注',
    status VARCHAR(255) COMMENT '状态',
    create_time DATETIME COMMENT '创建时间',
    create_userid INT COMMENT '创建用户 ID',
    update_time DATETIME COMMENT '更新时间',
    update_userid INT COMMENT '更新用户 ID',
    is_del SMALLINT COMMENT '是否删除'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤排班表-每个排班项目可以有多个排班';

-- 4. imoc_class_duty_user 考勤人员排班记录表
CREATE TABLE imoc_class_duty_user (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    userid INT COMMENT '用户 ID',
    project_id INT COMMENT '项目 ID',
    duty_id INT COMMENT '排班 ID',
    class_id INT COMMENT '班次 ID',
    team_id INT COMMENT '队伍 ID',
    duty_date DATE COMMENT '值班日期',
    duty_time TEXT COMMENT '考勤时间',
    duty_status TEXT COMMENT '考勤状态',
    checkin_time TEXT COMMENT '签到时间',
    checkin_location TEXT COMMENT '签到位置',
    type VARCHAR(255) COMMENT '值班类型',
    status VARCHAR(255) COMMENT '状态',
    create_time DATETIME COMMENT '创建时间',
    update_time DATETIME COMMENT '更新时间',
    is_del SMALLINT COMMENT '是否删除'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤人员排班记录表-人员每一天具体上什么班次';

-- 5. imoc_class_project 考勤排班项目表
CREATE TABLE imoc_class_project (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    name VARCHAR(255) NOT NULL COMMENT '项目名称',
    is_insance SMALLINT NOT NULL COMMENT '是否重保',
    create_time DATETIME NOT NULL COMMENT '创建时间',
    create_userid INT NOT NULL COMMENT '创建用户 ID',
    update_time DATETIME NOT NULL COMMENT '更新时间',
    update_userid INT NOT NULL COMMENT '更新用户 ID',
    is_del SMALLINT NOT NULL COMMENT '是否删除',
    status VARCHAR(255) NOT NULL COMMENT '状态'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤排班项目表';

-- 6. imoc_class_range 考勤班次时段表
CREATE TABLE imoc_class_range (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    class_id INT NOT NULL COMMENT '班次ID',
    start_time VARCHAR(255) NOT NULL COMMENT '开始时间',
    end_time VARCHAR(255) NOT NULL COMMENT '结束时间',
    tertian SMALLINT NOT NULL COMMENT '是否隔日'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤班次时段表-每个班次可以有多个上班时间段';

-- 7. imoc_class_team 考勤团队表
CREATE TABLE imoc_class_team (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    user_id INT COMMENT '用户 ID',
    project_id INT COMMENT '项目 ID',
    class_id INT COMMENT '班次 ID',
    duty_id INT COMMENT '排班 ID'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤团队表';

-- 8. imoc_class_user 考勤人员记录表
CREATE TABLE imoc_class_user (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT '主键',
    userid INT COMMENT '用户 ID',
    groupid INT COMMENT '部门 ID',
    type VARCHAR(255) COMMENT '适用对象',
    mobile VARCHAR(255) COMMENT '手机号码',
    location TEXT COMMENT '位置',
    create_time DATETIME COMMENT '创建时间',
    create_userid INT COMMENT '创建用户 ID',
    update_time DATETIME COMMENT '更新时间',
    update_userid INT COMMENT '更新用户 ID',
    is_del SMALLINT COMMENT '是否删除',
    name VARCHAR(255) COMMENT '姓名'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤人员记录表';

-- 9. imoc_class_appeal 考勤申诉表
CREATE TABLE imoc_class_appeal (
    id INT AUTO_INCREMENT PRIMARY KEY COMMENT 'ID',
    duty_id INT COMMENT '值班ID',
    type VARCHAR(255) COMMENT '类型',
    start_time DATETIME COMMENT '开始时间',
    end_time DATETIME COMMENT '结束时间',
    reson VARCHAR(255) COMMENT '请假原因',
    pic_url TEXT COMMENT '请假图片',
    status VARCHAR(255) COMMENT '状态',
    reject_reson VARCHAR(255) COMMENT '拒绝理由',
    gov_reject_reson VARCHAR(255) COMMENT '业主拒绝理由',
    create_userid INT COMMENT '申请人uid',
    create_time DATETIME COMMENT '申请时间',
    update_time DATETIME COMMENT '更新时间',
    approve_user VARCHAR(255) COMMENT '审批人员',
    approve_userid INT COMMENT '审批人ID',
    approve_time DATETIME COMMENT '审批时间',
    gov_approve_user VARCHAR(255) COMMENT '业主审批人员',
    gov_approve_userid INT COMMENT '业主审批人ID',
    gov_approve_time DATETIME COMMENT '业主审批时间',
    is_del SMALLINT DEFAULT 0 COMMENT '是否删除'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='考勤申诉表-异常考勤可以申请申诉，申诉通过后可以订正为正常状态';