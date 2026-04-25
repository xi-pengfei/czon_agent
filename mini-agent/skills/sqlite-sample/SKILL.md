---
name: sqlite-sample
description: Query the sample SQLite employee database. Use when the user asks about employees, salaries, departments, or wants to demonstrate database query capabilities.
---

# SQLite Sample Skill

This skill queries a sample SQLite database containing employee data.

## Database Location

`data/sample.db`

## Table Structure

See `skills/sqlite-sample/references/schema.md` for full schema.

The main table is `employees` with columns:
- `id` INTEGER PRIMARY KEY
- `name` TEXT — employee name
- `department` TEXT — department name
- `salary` REAL — monthly salary (CNY)
- `hire_date` TEXT — hire date (YYYY-MM-DD)

Departments: 工程部, 产品部, 市场部, 财务部, 人力资源部

## How to Query

Run the query script with a SELECT statement:

    bash: python skills/sqlite-sample/scripts/query.py --sql "SELECT * FROM employees LIMIT 5"

The script outputs results as JSON to stdout.

## Query Examples

1. 查询全部员工：
   `python skills/sqlite-sample/scripts/query.py --sql "SELECT * FROM employees"`

2. 按部门统计平均薪资：
   `python skills/sqlite-sample/scripts/query.py --sql "SELECT department, AVG(salary) as avg_salary FROM employees GROUP BY department ORDER BY avg_salary DESC"`

3. 查询薪资最高的 3 名员工：
   `python skills/sqlite-sample/scripts/query.py --sql "SELECT name, department, salary FROM employees ORDER BY salary DESC LIMIT 3"`

4. 查询特定员工：
   `python skills/sqlite-sample/scripts/query.py --sql "SELECT * FROM employees WHERE name = '张伟'"`

5. 查询入职超过 5 年的员工：
   `python skills/sqlite-sample/scripts/query.py --sql "SELECT * FROM employees WHERE hire_date <= '2020-04-18'"`

## Safety Rules

- **只允许 SELECT 查询**，脚本会拒绝 INSERT / UPDATE / DELETE / DROP 等操作
- 默认自动添加 LIMIT 100，防止返回过多数据
- 数据库路径固定为 `data/sample.db`，不可修改

## Setup

如果 `data/sample.db` 不存在，先运行：
    `python main.py setup`
