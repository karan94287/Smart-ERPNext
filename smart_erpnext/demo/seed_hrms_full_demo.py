"""Seed complete HRMS demo: recruitment + leave, payroll, attendance, expense, advances.

Run:
    bench --site smart.com execute smart_erpnext.demo.seed_hrms_full_demo.run
"""

from __future__ import annotations

import frappe
from frappe.utils import (
	add_days,
	add_months,
	get_first_day,
	get_last_day,
	get_year_ending,
	get_year_start,
	getdate,
	today,
)

from smart_erpnext.demo.seed_hrms_demo import seed as seed_recruitment

COMPANY = "karan (Demo)"
PREFIX = "DEMO"
HOLIDAY_LIST = f"{PREFIX} Holiday List"
COST_CENTER = "Main - KD"
LEAVE_APPROVER = "Administrator"


def run():
	frappe.set_user("Administrator")
	frappe.flags.in_import = True
	try:
		recruitment = seed_recruitment()
		operations = seed_operations()
		result = {**recruitment, **operations}
	finally:
		frappe.flags.in_import = False
		frappe.db.commit()
		frappe.clear_cache()

	print_summary(result)
	return result


def seed_operations():
	created = {
		"leave": [],
		"payroll": [],
		"attendance": [],
		"expense": [],
		"employees": [],
	}
	company = COMPANY

	ensure_company_hr_settings(company, created)
	employees = configure_employees(company, created)

	leave_types = ensure_leave_types(created)
	leave_period = ensure_leave_period(company, created)
	leave_policy = ensure_leave_policy(leave_types, created)
	ensure_leave_policy_assignments(employees, leave_policy, created)
	ensure_leave_applications(employees, leave_types, company, created)

	components = ensure_salary_components(company, created)
	salary_structure = ensure_salary_structure(company, components, created)
	ensure_salary_structure_assignments(employees, salary_structure, company, created)
	payroll_period = ensure_payroll_period(company, created)
	ensure_salary_slips(employees, salary_structure, payroll_period, created)

	shift_type = ensure_shift_type(created)
	ensure_shift_assignments(employees, shift_type, company, created)
	ensure_attendance(employees, shift_type, leave_types, created)

	expense_type = ensure_expense_claim_type(company, created)
	ensure_expense_claim(employees[0], company, expense_type, created)
	ensure_employee_advance(employees[0], company, created)

	return {
		"company": company,
		"employees": employees,
		"leave_period": leave_period,
		"leave_policy": leave_policy,
		"salary_structure": salary_structure,
		"payroll_period": payroll_period,
		"shift_type": shift_type,
		"created_operations": created,
	}


# ── Company & Employees ───────────────────────────────────────────


def ensure_company_hr_settings(company, created):
	updates = {
		"default_holiday_list": HOLIDAY_LIST,
		"default_payroll_payable_account": "Payroll Payable - KD",
		"default_expense_claim_payable_account": "Creditors - KD",
		"default_employee_advance_account": "Debtors - KD",
	}
	frappe.db.set_value("Company", company, updates, update_modified=False)
	frappe.db.set_single_value("Payroll Settings", "email_salary_slip_to_employee", 0)
	created["employees"].append("Company HR accounts configured")


def configure_employees(company, created):
	joining = get_first_day(add_months(today(), -3))
	employees = frappe.get_all(
		"Employee",
		filters={"company": company, "status": "Active"},
		pluck="name",
		order_by="creation asc",
	)
	for employee in employees:
		frappe.db.set_value(
			"Employee",
			employee,
			{
				"holiday_list": HOLIDAY_LIST,
				"leave_approver": LEAVE_APPROVER,
				"expense_approver": LEAVE_APPROVER,
				"date_of_joining": joining,
			},
			update_modified=False,
		)
		created["employees"].append(f"Employee configured: {employee}")
	return employees


# ── Leave ─────────────────────────────────────────────────────────


def ensure_leave_types(created):
	specs = [
		{
			"name": "Casual Leave",
			"leave_type_name": "Casual Leave",
			"allow_encashment": 1,
			"is_carry_forward": 1,
			"max_continuous_days_allowed": 3,
			"include_holiday": 1,
		},
		{
			"name": "Sick Leave",
			"leave_type_name": "Sick Leave",
			"allow_encashment": 0,
			"is_carry_forward": 0,
			"include_holiday": 1,
		},
		{
			"name": "Privilege Leave",
			"leave_type_name": "Privilege Leave",
			"allow_encashment": 0,
			"is_carry_forward": 0,
			"include_holiday": 1,
		},
		{
			"name": "Leave Without Pay",
			"leave_type_name": "Leave Without Pay",
			"allow_encashment": 0,
			"is_carry_forward": 0,
			"is_lwp": 1,
			"include_holiday": 1,
		},
	]
	names = []
	for spec in specs:
		if not frappe.db.exists("Leave Type", spec["name"]):
			frappe.get_doc({"doctype": "Leave Type", **spec}).insert(ignore_permissions=True)
			created["leave"].append(f"Leave Type: {spec['name']}")
		names.append(spec["name"])
	return names


def ensure_leave_period(company, created):
	from_date = get_year_start(today())
	to_date = get_year_ending(today())
	existing = frappe.db.get_value(
		"Leave Period",
		{"company": company, "from_date": from_date, "to_date": to_date},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Leave Period",
			"from_date": from_date,
			"to_date": to_date,
			"company": company,
			"is_active": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	created["leave"].append(f"Leave Period: {doc.name}")
	return doc.name


def ensure_leave_policy(leave_types, created):
	title = f"{PREFIX} Standard Leave Policy"
	existing = frappe.db.get_value("Leave Policy", {"title": title, "docstatus": 1}, "name")
	if existing:
		return existing

	allocations = {
		"Casual Leave": 12,
		"Sick Leave": 6,
		"Privilege Leave": 15,
	}
	doc = frappe.get_doc({"doctype": "Leave Policy", "title": title})
	for leave_type in leave_types:
		if leave_type in allocations:
			doc.append("leave_policy_details", {"leave_type": leave_type, "annual_allocation": allocations[leave_type]})
	doc.insert(ignore_permissions=True)
	submit_doc(doc)
	created["leave"].append(f"Leave Policy: {doc.name}")
	return doc.name


def ensure_leave_policy_assignments(employees, leave_policy, created):
	for employee in employees:
		existing = frappe.db.get_value(
			"Leave Policy Assignment",
			{"employee": employee, "leave_policy": leave_policy, "docstatus": 1},
			"name",
		)
		if existing:
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Leave Policy Assignment",
				"employee": employee,
				"leave_policy": leave_policy,
				"assignment_based_on": "Joining Date",
				"carry_forward": 0,
			}
		)
		doc.insert(ignore_permissions=True)
		submit_doc(doc)
		created["leave"].append(f"Leave Policy Assignment: {doc.name} ({employee})")


def ensure_leave_applications(employees, leave_types, company, created):
	if "Casual Leave" not in leave_types:
		return

	employee = employees[-1]
	from_date = add_days(today(), -10)
	to_date = add_days(from_date, 1)
	existing = frappe.db.get_value(
		"Leave Application",
		{
			"employee": employee,
			"leave_type": "Casual Leave",
			"from_date": from_date,
			"docstatus": 1,
		},
		"name",
	)
	if existing:
		return

	doc = frappe.get_doc(
		{
			"doctype": "Leave Application",
			"employee": employee,
			"leave_type": "Casual Leave",
			"from_date": from_date,
			"to_date": to_date,
			"posting_date": today(),
			"company": company,
			"description": f"{PREFIX} demo casual leave",
			"leave_approver": LEAVE_APPROVER,
			"status": "Approved",
		}
	)
	doc.insert(ignore_permissions=True)
	submit_doc(doc)
	created["leave"].append(f"Leave Application: {doc.name} ({employee})")


# ── Payroll ───────────────────────────────────────────────────────


def ensure_salary_components(company, created):
	specs = [
		{"salary_component": "Basic", "salary_component_abbr": "B", "type": "Earning", "amount": 50000},
		{"salary_component": "House Rent Allowance", "salary_component_abbr": "HRA", "type": "Earning", "amount": 0},
		{"salary_component": "Professional Tax", "salary_component_abbr": "PT", "type": "Deduction", "amount": 200},
	]
	names = []
	for spec in specs:
		name = spec["salary_component"]
		if frappe.db.exists("Salary Component", name):
			names.append(name)
			continue

		doc = frappe.get_doc({"doctype": "Salary Component", **spec})
		doc.append(
			"accounts",
			{
				"company": company,
				"account": "Salary - KD" if spec["type"] == "Earning" else "Payroll Payable - KD",
			},
		)
		doc.insert(ignore_permissions=True)
		created["payroll"].append(f"Salary Component: {name}")
		names.append(name)
	return names


def ensure_salary_structure(company, components, created):
	name = f"{PREFIX} Monthly Salary"
	existing = frappe.db.get_value("Salary Structure", {"name": name, "docstatus": 1}, "name")
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Salary Structure",
			"name": name,
			"company": company,
			"payroll_frequency": "Monthly",
			"currency": frappe.db.get_value("Company", company, "default_currency"),
			"payment_account": "Payroll Payable - KD",
			"is_active": "Yes",
		}
	)
	doc.append("earnings", {"salary_component": "Basic", "amount": 50000})
	doc.append(
		"earnings",
		{
			"salary_component": "House Rent Allowance",
			"amount_based_on_formula": 1,
			"formula": "base * 0.40",
		},
	)
	doc.append("deductions", {"salary_component": "Professional Tax", "amount": 200})
	doc.insert(ignore_permissions=True)
	submit_doc(doc)
	created["payroll"].append(f"Salary Structure: {name}")
	return name


def ensure_salary_structure_assignments(employees, salary_structure, company, created):
	from_date = get_first_day(add_months(today(), -3))
	currency = frappe.db.get_value("Company", company, "default_currency")

	for employee in employees:
		existing = frappe.db.get_value(
			"Salary Structure Assignment",
			{"employee": employee, "salary_structure": salary_structure, "docstatus": 1},
			"name",
		)
		if existing:
			continue

		joining = frappe.db.get_value("Employee", employee, "date_of_joining")
		assignment_from = max(getdate(from_date), getdate(joining))

		doc = frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment",
				"employee": employee,
				"salary_structure": salary_structure,
				"from_date": assignment_from,
				"company": company,
				"currency": currency,
				"base": 50000,
				"payroll_payable_account": "Payroll Payable - KD",
			}
		)
		doc.insert(ignore_permissions=True)
		submit_doc(doc)
		created["payroll"].append(f"Salary Structure Assignment: {doc.name} ({employee})")


def ensure_payroll_period(company, created):
	name = f"{PREFIX} Payroll Period {today()[:4]}"
	if frappe.db.exists("Payroll Period", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Payroll Period",
			"name": name,
			"company": company,
			"start_date": get_year_start(today()),
			"end_date": get_year_ending(today()),
		}
	)
	doc.insert(ignore_permissions=True)
	created["payroll"].append(f"Payroll Period: {name}")
	return name


def ensure_salary_slips(employees, salary_structure, payroll_period, created):
	from hrms.payroll.doctype.salary_structure.salary_structure import make_salary_slip

	posting_date = add_days(get_first_day(add_months(today(), -1)), 25)
	start_date = get_first_day(posting_date)
	end_date = get_last_day(posting_date)

	for employee in employees:
		existing = frappe.db.get_value(
			"Salary Slip",
			{
				"employee": employee,
				"start_date": start_date,
				"end_date": end_date,
				"docstatus": 1,
			},
			"name",
		)
		if existing:
			continue

		slip = make_salary_slip(
			salary_structure,
			employee=employee,
			posting_date=posting_date,
			ignore_permissions=True,
		)
		slip.insert(ignore_permissions=True)
		submit_doc(slip)
		created["payroll"].append(f"Salary Slip: {slip.name} ({employee})")


# ── Attendance & Shifts ───────────────────────────────────────────


def ensure_shift_type(created):
	name = f"{PREFIX} Day Shift"
	if frappe.db.exists("Shift Type", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Shift Type",
			"name": name,
			"start_time": "09:00:00",
			"end_time": "18:00:00",
			"holiday_list": HOLIDAY_LIST,
		}
	)
	doc.insert(ignore_permissions=True)
	created["attendance"].append(f"Shift Type: {name}")
	return name


def ensure_shift_assignments(employees, shift_type, company, created):
	start_date = get_first_day(add_months(today(), -1))
	end_date = get_year_ending(today())

	for employee in employees:
		existing = frappe.db.get_value(
			"Shift Assignment",
			{
				"employee": employee,
				"shift_type": shift_type,
				"docstatus": 1,
				"start_date": start_date,
			},
			"name",
		)
		if existing:
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": employee,
				"shift_type": shift_type,
				"company": company,
				"start_date": start_date,
				"end_date": end_date,
			}
		)
		doc.insert(ignore_permissions=True)
		submit_doc(doc)
		created["attendance"].append(f"Shift Assignment: {doc.name} ({employee})")


def ensure_attendance(employees, shift_type, leave_types, created):
	from hrms.hr.doctype.attendance.attendance import mark_attendance

	leave_employee = employees[-1]
	leave_from = getdate(add_days(today(), -10))
	leave_to = getdate(add_days(leave_from, 1))

	for employee in employees:
		joining = getdate(frappe.db.get_value("Employee", employee, "date_of_joining"))
		current = max(joining, getdate(add_days(today(), -14)))
		end = getdate(today())
		while current < end:
			if current.weekday() >= 5:
				current = getdate(add_days(current, 1))
				continue

			if frappe.db.exists(
				"Attendance",
				{"employee": employee, "attendance_date": current, "docstatus": 1},
			):
				current = getdate(add_days(current, 1))
				continue

			if employee == leave_employee and leave_from <= current <= leave_to:
				status = "On Leave"
				leave_type = "Casual Leave"
			elif current == getdate(add_days(today(), -3)) and employee == employees[0]:
				status = "Half Day"
				leave_type = None
			else:
				status = "Present"
				leave_type = None

			mark_attendance(
				employee,
				current,
				status,
				shift=shift_type,
				leave_type=leave_type,
				half_day_status="Present" if status == "Half Day" else None,
			)
			created["attendance"].append(f"Attendance: {employee} {current} → {status}")
			current = getdate(add_days(current, 1))


# ── Expense & Advances ────────────────────────────────────────────


def ensure_expense_claim_type(company, created):
	name = f"{PREFIX} Travel"
	if frappe.db.exists("Expense Claim Type", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Expense Claim Type",
			"expense_type": name,
			"description": f"{PREFIX} business travel",
		}
	)
	doc.append(
		"accounts",
		{"company": company, "default_account": "Travel Expenses - KD"},
	)
	doc.insert(ignore_permissions=True)
	created["expense"].append(f"Expense Claim Type: {name}")
	return name


def ensure_expense_claim(employee, company, expense_type, created):
	existing = frappe.db.get_value(
		"Expense Claim",
		{"employee": employee, "approval_status": "Approved", "docstatus": 1},
		"name",
	)
	if existing:
		return existing

	currency = frappe.db.get_value("Company", company, "default_currency")
	doc = frappe.get_doc(
		{
			"doctype": "Expense Claim",
			"employee": employee,
			"company": company,
			"posting_date": today(),
			"approval_status": "Approved",
			"expense_approver": LEAVE_APPROVER,
			"payable_account": "Creditors - KD",
			"currency": currency,
			"expenses": [
				{
					"expense_type": expense_type,
					"default_account": "Travel Expenses - KD",
					"amount": 2500,
					"sanctioned_amount": 2500,
					"cost_center": COST_CENTER,
					"currency": currency,
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)
	submit_doc(doc)
	created["expense"].append(f"Expense Claim: {doc.name} ({employee})")
	return doc.name


def ensure_employee_advance(employee, company, created):
	existing = frappe.db.get_value(
		"Employee Advance",
		{"employee": employee, "docstatus": 1},
		"name",
	)
	if existing:
		return existing

	currency = frappe.db.get_value("Company", company, "default_currency")
	doc = frappe.get_doc(
		{
			"doctype": "Employee Advance",
			"employee": employee,
			"company": company,
			"posting_date": today(),
			"purpose": f"{PREFIX} travel advance",
			"advance_amount": 5000,
			"advance_account": "Debtors - KD",
			"mode_of_payment": "Cash",
			"currency": currency,
			"exchange_rate": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	submit_doc(doc)
	created["expense"].append(f"Employee Advance: {doc.name} ({employee})")
	return doc.name


# ── Helpers ───────────────────────────────────────────────────────


def submit_doc(doc):
	frappe.flags.in_test = True
	try:
		doc.submit()
	finally:
		frappe.flags.in_test = False


def print_summary(result):
	ops = result.get("created_operations", {})
	print("\n" + "=" * 60)
	print("FULL HRMS DEMO DATA CREATED")
	print("=" * 60)
	print(f"Company            : {result.get('company', COMPANY)}")
	print(f"Employees          : {', '.join(result.get('employees', []))}")
	print()
	print("Recruitment (from seed_hrms_demo):")
	print(f"  Hired Employee   → {result.get('hired_employee')}")
	print(f"  Job Opening      → {result.get('job_opening')}")
	print()
	print("Leave & Attendance:")
	print(f"  Leave Period     → {result.get('leave_period')}")
	print(f"  Leave Policy     → {result.get('leave_policy')}")
	print(f"  Shift Type       → {result.get('shift_type')}")
	for line in ops.get("leave", [])[:6]:
		print(f"  • {line}")
	for line in ops.get("attendance", [])[:4]:
		print(f"  • {line}")
	print()
	print("Payroll:")
	print(f"  Salary Structure → {result.get('salary_structure')}")
	print(f"  Payroll Period   → {result.get('payroll_period')}")
	for line in ops.get("payroll", [])[:6]:
		print(f"  • {line}")
	print()
	print("Expense & Advances:")
	for line in ops.get("expense", []):
		print(f"  • {line}")
	print("=" * 60)
