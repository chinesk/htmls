from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
from io import BytesIO
import base64
import os
import calendar
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)

# 配置matplotlib支持中文
plt.rcParams['font.sans-serif'] = ['SimHei']  # Windows系统使用SimHei
plt.rcParams['axes.unicode_minus'] = False     # 解决负号显示问题

# 定义值班岗位
POSITIONS = ['车间领导班', '车间班', '车间领导副班', '值班干事', '内院白班', '内院夜班']

# 添加显示用的岗位（用于添加人员时显示）
DISPLAY_POSITIONS = ['领导组', '车间班', '值班干事', '内院组']

# 添加这个新的常量定义
POSITION_GROUPS = ['领导组', '车间班', '值班干事', '内院组']

# 定义岗位映射关系
POSITION_MAPPING = {
    '领导组': ['车间领导班', '车间领导副班'],
    '内院组': ['内院白班', '内院夜班'],
    '车间班': ['车间班'],
    '值班干事': ['值班干事']
}

# 反向映射，用于确定人员所属组
REVERSE_POSITION_MAPPING = {
    '车间领导班': '领导组',
    '车间领导副班': '领导组',
    '内院白班': '内院组',
    '内院夜班': '内院组',
    '车间班': '车间班',
    '值班干事': '值班干事'
}

def init_db():
    """初始化数据库"""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    # 创建值班人员表
    c.execute('''CREATE TABLE IF NOT EXISTS staff
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT UNIQUE,
                  position TEXT,
                  staff_group TEXT)''')  # 添加人员组字段
    
    # 创建值班安排表
    c.execute('''CREATE TABLE IF NOT EXISTS duty_schedule
                 (date TEXT,
                  position TEXT,
                  staff_name TEXT,
                  PRIMARY KEY (date, position))''')
    
    conn.commit()
    conn.close()

    print("数据库初始化完成！")

def get_duty_stats():
    """获取值班统计图"""
    conn = sqlite3.connect('database.db')
    df = pd.read_sql_query("""
        SELECT staff_name, COUNT(*) as count 
        FROM duty_schedule 
        GROUP BY staff_name
        ORDER BY count DESC""", conn)
    conn.close()
    
    if df.empty:
        return ""
    
    plt.figure(figsize=(12, 6))
    ax = df.plot(kind='bar', x='staff_name', y='count', color='skyblue')
    plt.title('值班人员值班次数统计', fontsize=14, pad=20)
    plt.xlabel('值班人员', fontsize=12)
    plt.ylabel('值班次数', fontsize=12)
    plt.xticks(rotation=45, ha='right')
    plt.grid(axis='y', alpha=0.3)
    
    # 添加数值标签
    for p in ax.patches:
        ax.annotate(f'{int(p.get_height())}', 
                   (p.get_x() + p.get_width()/2., p.get_height()),
                   ha='center', va='bottom')
    
    plt.tight_layout()
    
    img = BytesIO()
    plt.savefig(img, format='png', dpi=300, bbox_inches='tight')
    plt.close()
    img.seek(0)
    return base64.b64encode(img.getvalue()).decode()

@app.route('/')
def index():
    """首页 - 值班表"""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    
    try:
        # 获取所有值班人员及其岗位
        c.execute("SELECT name, position FROM staff ORDER BY name")
        staff_data = c.fetchall()
        
        # 按岗位分组值班人员，同时处理组内共享人员
        staff_by_position = {}
        for name, position in staff_data:
            # 获取该人员所属的组
            group = REVERSE_POSITION_MAPPING.get(position)
            
            if group == '领导组':
                # 领导组的人员可以在车间领导班和车间领导副班中选择
                positions = ['车间领导班', '车间领导副班']
                for pos in positions:
                    if pos not in staff_by_position:
                        staff_by_position[pos] = []
                    if name not in staff_by_position[pos]:
                        staff_by_position[pos].append(name)
                        
            elif group == '内院组':
                # 内院组的人员可以在内院白班和内院夜班中选择
                positions = ['内院白班', '内院夜班']
                for pos in positions:
                    if pos not in staff_by_position:
                        staff_by_position[pos] = []
                    if name not in staff_by_position[pos]:
                        staff_by_position[pos].append(name)
            else:
                # 其他岗位正常处理
                if position not in staff_by_position:
                    staff_by_position[position] = []
                if name not in staff_by_position[position]:
                    staff_by_position[position].append(name)
        
        # 获取当前月份的值班安排
        current_year = datetime.now().year
        current_month = datetime.now().month
        _, last_day = calendar.monthrange(current_year, current_month)
        
        # 获取本月所有值班安排
        c.execute("""
            SELECT date, position, staff_name 
            FROM duty_schedule 
            WHERE date LIKE ?
        """, (f"{current_year}-{current_month:02d}-%",))
        schedule_data = c.fetchall()
        
        # 创建值班安排字典
        schedule = {}
        for date, position, staff_name in schedule_data:
            schedule[(date, position)] = staff_name
        
        return render_template('index.html',
                             staff_by_position=staff_by_position,
                             positions=POSITIONS,  # 使用原有的完整岗位列表
                             schedule=schedule,
                             stats_img=get_duty_stats(),
                             days_range=range(1, last_day + 1),
                             current_year=current_year,
                             current_month=current_month)
    finally:
        conn.close()
    
    return render_template('index.html',
                         staff_by_position=staff_by_position,
                         positions=POSITIONS,
                         schedule=schedule,
                         stats_img=get_duty_stats(),
                         days_range=range(1, last_day + 1),
                         current_year=current_year,
                         current_month=current_month)

@app.route('/staff')
def staff():
    """人员管理页面"""
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute("SELECT id, name, position FROM staff ORDER BY name")
    staff = c.fetchall()
    
    # 转换岗位显示
    staff_display = []
    for id, name, position in staff:
        display_position = REVERSE_POSITION_MAPPING.get(position, position)
        staff_display.append((id, name, display_position))
    
    conn.close()
    return render_template('staff.html', 
                         staff=staff_display, 
                         display_positions=DISPLAY_POSITIONS,
                         position_groups=POSITION_GROUPS)  # 添加这一行

@app.route('/add_staff', methods=['POST'])
def add_staff():
    """添加值班人员"""
    name = request.form['name'].strip()
    position_group = request.form['position'].strip()
    
    if not name or not position_group:
        return redirect(url_for('staff'))
    
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    try:
        # 获取该组的所有具体岗位
        positions = POSITION_MAPPING.get(position_group, [position_group])
        
        # 为每个具体岗位添加人员
        for position in positions:
            try:
                c.execute("INSERT INTO staff (name, position) VALUES (?, ?)", 
                         (name, position))
            except sqlite3.IntegrityError:
                # 如果已存在该人员，跳过
                continue
        
        conn.commit()
    except Exception as e:
        print(f"添加用户时发生错误: {str(e)}")
        conn.rollback()
    finally:
        conn.close()
    
    return redirect(url_for('staff'))

@app.route('/delete_staff/<int:id>')
def delete_staff(id):
    """删除值班人员"""
    conn = sqlite3.connect('database.db')
    try:
        # 首先删除该人员的所有值班安排
        c = conn.cursor()
        c.execute("SELECT name FROM staff WHERE id=?", (id,))
        name = c.fetchone()[0]
        c.execute("DELETE FROM duty_schedule WHERE staff_name=?", (name,))
        # 然后删除人员
        c.execute("DELETE FROM staff WHERE id=?", (id,))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for('staff'))

@app.route('/update_duty', methods=['POST'])
def update_duty():
    """更新值班安排"""
    date = request.form['date']
    position = request.form['position']
    staff_name = request.form['staff_name']
    
    conn = sqlite3.connect('database.db')
    try:
        if staff_name:
            conn.execute("""INSERT OR REPLACE INTO duty_schedule 
                          (date, position, staff_name) VALUES (?, ?, ?)""",
                       (date, position, staff_name))
        else:
            conn.execute("""DELETE FROM duty_schedule 
                          WHERE date=? AND position=?""",
                       (date, position))
        conn.commit()
        
        # 立即生成新的统计图
        new_stats_img = get_duty_stats()
        return jsonify({
            'success': True,
            'stats_img': new_stats_img
        })
    except Exception as e:
        conn.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })
    finally:
        conn.close()
    
    return jsonify({'stats_img': get_duty_stats()})
    
    # 生成新的统计图表
    stats_img = get_duty_stats()
    
    # 返回 JSON 响应，包含统计图表数据
    return jsonify({'stats_img': stats_img})

if __name__ == '__main__':
    # 确保templates目录存在
    if not os.path.exists('templates'):
        os.makedirs('templates')
    
    # 只在数据库不存在时初始化
    if not os.path.exists('database.db'):
        print("数据库不存在，正在初始化...")
        init_db()
    else:
        print("数据库已存在，跳过初始化！")
    
    # 运行应用
    app.run(debug=True)