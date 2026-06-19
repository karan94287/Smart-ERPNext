"""Seed end-to-end HRMS recruitment → onboarding demo data.

Run:
    bench --site smart.com execute smart_erpnext.demo.seed_hrms_demo.run
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate, today

COMPANY = "karan (Demo)"
PREFIX = "DEMO"
DESIGNATION = "Business Analyst"
DEPARTMENT = "Human Resources - KD"


def run():
	frappe.set_user("Administrator")
	frappe.flags.in_import = True
	try:
		result = seed()
	finally:
		frappe.flags.in_import = False
		frappe.db.commit()
		frappe.clear_cache()

	print_summary(result)
	return result


def seed():
	created = {"masters": [], "recruitment": [], "onboarding": []}
	company = COMPANY
	department = DEPARTMENT
	designation = DESIGNATION

	employment_type = ensure_employment_type(created)
	source = ensure_job_applicant_source(created)
	holiday_list = ensure_holiday_list(company, created)
	skill = ensure_skill(created)
	interview_type = ensure_interview_type(created)
	interview_round = ensure_interview_round(designation, skill, interview_type, created)
	onboarding_template = ensure_onboarding_template(company, department, designation, created)

	# HR employee needed for Job Requisition requested_by
	hr_employee = ensure_hr_employee(company, department, created)

	requisition = ensure_job_requisition(
		company, department, designation, hr_employee, employment_type, created
	)
	job_opening = ensure_job_opening(company, department, designation, requisition, created)

	# Applicant 1 — full hire flow
	applicant1 = ensure_job_applicant(
		job_opening,
		designation,
		"Rohit Sharma",
		"demo.rohit.hrms@example.com",
		"9876600001",
		source,
		created,
	)
	interview1 = ensure_interview(applicant1, job_opening, interview_round, designation, created)
	ensure_interview_feedback(interview1, interview_round, skill, created)
	submit_interview_cleared(interview1, applicant1, created)
	offer1 = ensure_job_offer(applicant1, company, designation, created)
	onboarding1 = ensure_employee_onboarding(
		applicant1, offer1, company, department, designation, onboarding_template, holiday_list, created
	)
	employee1 = ensure_employee_from_offer(applicant1, offer1, company, department, designation, created)

	# Applicant 2 — pipeline (applied, interview pending)
	applicant2 = ensure_job_applicant(
		job_opening,
		designation,
		"Neha Kapoor",
		"demo.neha.hrms@example.com",
		"9876600002",
		source,
		created,
		status="Open",
	)
	interview2 = ensure_interview(
		applicant2,
		job_opening,
		interview_round,
		designation,
		created,
		status="Pending",
		scheduled_on=add_days(today(), 2),
		submit=False,
	)

	# Applicant 3 — rejected
	applicant3 = ensure_job_applicant(
		job_opening,
		designation,
		"Vikram Patel",
		"demo.vikram.hrms@example.com",
		"9876600003",
		source,
		created,
	)
	interview3 = ensure_interview(applicant3, job_opening, interview_round, designation, created)
	ensure_interview_feedback(interview3, interview_round, skill, created, rating=0.3)
	submit_interview_cleared(interview3, applicant3, created, status="Rejected", applicant_status="Rejected")

	return {
		"company": company,
		"hr_employee": hr_employee,
		"job_requisition": requisition,
		"job_opening": job_opening,
		"hired_applicant": applicant1,
		"hired_employee": employee1,
		"job_offer": offer1,
		"employee_onboarding": onboarding1,
		"pipeline_applicant": applicant2,
		"pipeline_interview": interview2,
		"rejected_applicant": applicant3,
		"created_log": created,
	}


# ── Masters ───────────────────────────────────────────────────────


def ensure_employment_type(created):
	name = f"{PREFIX} Full-time"
	if frappe.db.exists("Employment Type", name):
		return name
	frappe.get_doc({"doctype": "Employment Type", "employee_type_name": name}).insert(
		ignore_permissions=True
	)
	created["masters"].append(f"Employment Type: {name}")
	return name


def ensure_job_applicant_source(created):
	name = f"{PREFIX} LinkedIn"
	if frappe.db.exists("Job Applicant Source", name):
		return name
	frappe.get_doc({"doctype": "Job Applicant Source", "source_name": name}).insert(
		ignore_permissions=True
	)
	created["masters"].append(f"Job Applicant Source: {name}")
	return name


def ensure_holiday_list(company, created):
	name = f"{PREFIX} Holiday List"
	if frappe.db.exists("Holiday List", name):
		return name
	doc = frappe.get_doc(
		{
			"doctype": "Holiday List",
			"holiday_list_name": name,
			"from_date": f"{getdate().year}-01-01",
			"to_date": f"{getdate().year}-12-31",
		}
	)
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"Holiday List: {name}")
	return name


def ensure_skill(created):
	name = f"{PREFIX} Communication"
	if frappe.db.exists("Skill", name):
		return name
	frappe.get_doc({"doctype": "Skill", "skill_name": name}).insert(ignore_permissions=True)
	created["masters"].append(f"Skill: {name}")
	return name


def ensure_interview_type(created):
	name = f"{PREFIX} Technical Round"
	if frappe.db.exists("Interview Type", name):
		return name
	frappe.get_doc({"doctype": "Interview Type", "name": name}).insert(ignore_permissions=True)
	created["masters"].append(f"Interview Type: {name}")
	return name


def ensure_interview_round(designation, skill, interview_type, created):
	name = f"{PREFIX} HR Interview Round"
	if frappe.db.exists("Interview Round", name):
		return name
	doc = frappe.get_doc(
		{
			"doctype": "Interview Round",
			"round_name": name,
			"designation": designation,
			"interview_type": interview_type,
			"expected_average_rating": 0.6,
		}
	)
	doc.append("expected_skill_set", {"skill": skill})
	doc.append("interviewers", {"user": "Administrator"})
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"Interview Round: {name}")
	return name


def ensure_onboarding_template(company, department, designation, created):
	title = f"{PREFIX} Standard Onboarding"
	existing = frappe.db.get_value("Employee Onboarding Template", {"title": title})
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Employee Onboarding Template",
			"title": title,
			"company": company,
			"department": department,
			"designation": designation,
		}
	)
	activities = [
		("Collect ID Documents", 0, 1, 1, 1),
		("Create Email Account", 1, 1, 1, 0),
		("Assign Laptop", 2, 2, 1, 0),
		("HR Orientation", 3, 1, 1, 0),
		("Department Introduction", 4, 2, 1, 0),
	]
	for activity_name, begin_on, duration, weight, required in activities:
		doc.append(
			"activities",
			{
				"activity_name": activity_name,
				"user": "Administrator",
				"begin_on": begin_on,
				"duration": duration,
				"task_weight": weight,
				"required_for_employee_creation": required,
				"description": f"{PREFIX} onboarding task — {activity_name}",
			},
		)
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"Onboarding Template: {doc.name}")
	return doc.name


def ensure_hr_employee(company, department, created):
	email = "demo.hr.manager@example.com"
	existing = frappe.db.get_value("Employee", {"user_id": "Administrator"}, "name")
	if not existing:
		existing = frappe.db.get_value("Employee", {"personal_email": email}, "name")
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Employee",
			"first_name": "Rahul",
			"last_name": "Mehta",
			"employee_name": f"{PREFIX} Rahul Mehta",
			"company": company,
			"department": department,
			"designation": "Administrative Officer",
			"gender": "Male",
			"date_of_birth": "1985-06-15",
			"date_of_joining": add_days(today(), -365),
			"status": "Active",
			"personal_email": email,
			"cell_number": "9876600100",
		}
	)
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"HR Employee: {doc.name}")
	return doc.name


# ── Recruitment flow ──────────────────────────────────────────────


def ensure_job_requisition(company, department, designation, hr_employee, employment_type, created):
	existing = frappe.db.get_value(
		"Job Requisition",
		{"designation": designation, "department": department, "company": company, "docstatus": 1},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Job Requisition",
			"naming_series": "HR-HIREQ-",
			"designation": designation,
			"department": department,
			"no_of_positions": 2,
			"expected_compensation": 600000,
			"company": company,
			"status": "Open & Approved",
			"requested_by": hr_employee,
			"posting_date": today(),
			"expected_by": add_days(today(), 30),
			"description": f"{PREFIX} hiring request for Business Analyst role",
			"reason_for_requesting": "Team expansion for demo purposes",
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.flags.in_test = True
	try:
		doc.submit()
	finally:
		frappe.flags.in_test = False
	created["recruitment"].append(f"Job Requisition: {doc.name}")
	return doc.name


def ensure_job_opening(company, department, designation, requisition, created):
	existing = frappe.db.get_value(
		"Job Opening", {"job_requisition": requisition, "company": company}, "name"
	)
	if existing:
		return existing

	from hrms.hr.doctype.job_requisition.job_requisition import make_job_opening

	doc = make_job_opening(requisition)
	doc.job_title = f"{PREFIX} Business Analyst"
	doc.employment_type = frappe.db.get_value("Employment Type", {"employee_type_name": ["like", f"{PREFIX}%"]})
	doc.description = f"{PREFIX} We are hiring a Business Analyst to join our team."
	doc.lower_range = 500000
	doc.upper_range = 800000
	doc.vacancies = 2
	doc.insert(ignore_permissions=True)
	created["recruitment"].append(f"Job Opening: {doc.name}")
	return doc.name


def ensure_job_applicant(
	job_opening,
	designation,
	name,
	email,
	phone,
	source,
	created,
	status="Open",
):
	existing = frappe.db.get_value("Job Applicant", {"email_id": email}, "name")
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Job Applicant",
			"applicant_name": name,
			"email_id": email,
			"phone_number": phone,
			"job_title": job_opening,
			"designation": designation,
			"status": status,
			"source": source,
			"country": "India",
			"cover_letter": f"{PREFIX} I am excited to apply for the Business Analyst role.",
		}
	)
	doc.insert(ignore_permissions=True)
	created["recruitment"].append(f"Job Applicant: {doc.name} ({name})")
	return doc.name


def ensure_interview(
	applicant,
	job_opening,
	interview_round,
	designation,
	created,
	status="Under Review",
	scheduled_on=None,
	submit=True,
):
	existing = frappe.db.exists(
		"Interview",
		{"job_applicant": applicant, "interview_round": interview_round, "docstatus": ["!=", 2]},
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Interview",
			"interview_round": interview_round,
			"job_applicant": applicant,
			"job_opening": job_opening,
			"designation": designation,
			"status": status,
			"scheduled_on": scheduled_on or today(),
			"from_time": "10:00:00",
			"to_time": "10:45:00",
		}
	)
	doc.append("interview_details", {"interviewer": "Administrator"})
	doc.insert(ignore_permissions=True)
	created["recruitment"].append(f"Interview: {doc.name} ({status})")
	return doc.name


def ensure_interview_feedback(interview, interview_round, skill, created, rating=0.8):
	existing = frappe.db.exists(
		"Interview Feedback",
		{"interview": interview, "interviewer": "Administrator", "docstatus": 1},
	)
	if existing:
		return existing

	applicant = frappe.db.get_value("Interview", interview, "job_applicant")
	doc = frappe.get_doc(
		{
			"doctype": "Interview Feedback",
			"interview": interview,
			"interview_round": interview_round,
			"job_applicant": applicant,
			"interviewer": "Administrator",
			"feedback": f"{PREFIX} structured interview feedback.",
			"result": "Cleared" if rating >= 0.5 else "Rejected",
		}
	)
	doc.append("skill_assessment", {"skill": skill, "rating": rating})
	doc.insert(ignore_permissions=True)
	frappe.flags.in_test = True
	try:
		doc.submit()
	finally:
		frappe.flags.in_test = False
	created["recruitment"].append(f"Interview Feedback: {doc.name}")
	return doc.name


def submit_interview_cleared(
	interview,
	applicant,
	created,
	status="Cleared",
	applicant_status="Accepted",
):
	doc = frappe.get_doc("Interview", interview)
	if doc.docstatus == 1:
		frappe.db.set_value("Job Applicant", applicant, "status", applicant_status)
		return interview

	doc.status = status
	doc.save(ignore_permissions=True)
	frappe.flags.in_test = True
	try:
		doc.submit()
	finally:
		frappe.flags.in_test = False
	frappe.db.set_value("Job Applicant", applicant, "status", applicant_status)
	created["recruitment"].append(f"Interview submitted: {interview} → {status}")
	return interview


def ensure_job_offer(applicant, company, designation, created):
	existing = frappe.db.get_value(
		"Job Offer", {"job_applicant": applicant, "docstatus": 1}, "name"
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Job Offer",
			"job_applicant": applicant,
			"offer_date": today(),
			"designation": designation,
			"company": company,
			"status": "Accepted",
		}
	)
	doc.insert(ignore_permissions=True)
	frappe.flags.in_test = True
	try:
		doc.submit()
	finally:
		frappe.flags.in_test = False
	created["recruitment"].append(f"Job Offer: {doc.name}")
	return doc.name


# ── Onboarding & Employee ─────────────────────────────────────────


def copy_template_activities(doc, template):
	from hrms.controllers.employee_boarding_controller import get_onboarding_details

	doc.activities = []
	for row in get_onboarding_details(template, "Employee Onboarding Template"):
		doc.append("activities", row)


def ensure_employee_onboarding(
	applicant,
	offer,
	company,
	department,
	designation,
	template,
	holiday_list,
	created,
):
	existing = frappe.db.get_value(
		"Employee Onboarding", {"job_applicant": applicant, "docstatus": 1}, "name"
	)
	if existing:
		doc = frappe.get_doc("Employee Onboarding", existing)
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Employee Onboarding",
				"job_applicant": applicant,
				"job_offer": offer,
				"employee_onboarding_template": template,
				"company": company,
				"department": department,
				"designation": designation,
				"holiday_list": holiday_list,
				"date_of_joining": today(),
				"boarding_begins_on": today(),
			}
		)
		copy_template_activities(doc, template)
		doc.insert(ignore_permissions=True)
		frappe.flags.in_test = True
		try:
			doc.submit()
		finally:
			frappe.flags.in_test = False
		created["onboarding"].append(f"Employee Onboarding: {doc.name}")

	doc = frappe.get_doc("Employee Onboarding", doc.name)
	# Complete mandatory onboarding tasks
	for activity in doc.activities:
		if activity.task:
			frappe.db.set_value("Task", activity.task, "status", "Completed")

	doc.reload()
	if doc.boarding_status != "Completed":
		doc.mark_onboarding_as_completed()

	created["onboarding"].append(f"Onboarding tasks completed: {doc.name}")
	return doc.name


def ensure_employee_from_offer(applicant, offer, company, department, designation, created):
	existing = frappe.db.get_value("Employee", {"job_applicant": applicant}, "name")
	if existing:
		return existing

	from hrms.hr.doctype.job_offer.job_offer import make_employee

	employee = make_employee(offer)
	employee.company = company
	employee.department = department
	employee.designation = designation
	employee.gender = "Male"
	employee.date_of_birth = "1996-04-10"
	employee.date_of_joining = today()
	employee.status = "Active"
	employee.job_applicant = applicant
	employee.personal_email = frappe.db.get_value("Job Applicant", applicant, "email_id")
	employee.cell_number = frappe.db.get_value("Job Applicant", applicant, "phone_number")

	# Split applicant name into first/last
	name = frappe.db.get_value("Job Applicant", applicant, "applicant_name") or "Demo Employee"
	parts = name.split(" ", 1)
	employee.first_name = parts[0]
	employee.last_name = parts[1] if len(parts) > 1 else ""
	employee.employee_name = name

	employee.insert(ignore_permissions=True)
	created["onboarding"].append(f"Employee: {employee.name} ({name})")
	return employee.name


def print_summary(result):
	print("\n" + "=" * 60)
	print("HRMS DEMO DATA CREATED")
	print("=" * 60)
	print(f"Company           : {result['company']}")
	print(f"HR Manager        : {result['hr_employee']}")
	print(f"Job Requisition   : {result['job_requisition']}")
	print(f"Job Opening       : {result['job_opening']}")
	print()
	print("Full hire flow (Rohit Sharma):")
	print(f"  Job Applicant     → {result['hired_applicant']}")
	print(f"  Job Offer         → {result['job_offer']}")
	print(f"  Employee Onboard  → {result['employee_onboarding']}")
	print(f"  Employee          → {result['hired_employee']}")
	print()
	print("Pipeline (Neha Kapoor):")
	print(f"  Job Applicant     → {result['pipeline_applicant']}")
	print(f"  Interview Pending → {result['pipeline_interview']}")
	print()
	print(f"Rejected applicant  → {result['rejected_applicant']}")
	print()
	print("Open in desk:")
	print("  /app/job-requisition")
	print("  /app/job-opening")
	print("  /app/job-applicant")
	print("  /app/interview")
	print("  /app/job-offer")
	print("  /app/employee-onboarding")
	print("  /app/employee")
	print("=" * 60)
