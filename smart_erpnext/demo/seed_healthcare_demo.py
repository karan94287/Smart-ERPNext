"""Seed end-to-end Healthcare demo data on smart.com.

Run:
    bench --site smart.com execute smart_erpnext.demo.seed_healthcare_demo.run
"""

from __future__ import annotations

import frappe
from frappe.utils import add_days, getdate, now_datetime, today

COMPANY = "karan (Demo)"
PREFIX = "DEMO"
DEPARTMENT = "Cardiology"


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


def get_department():
	if frappe.db.exists("Medical Department", DEPARTMENT):
		return DEPARTMENT
	return frappe.db.get_value("Medical Department", {}, "name") or "Cardiology"


def seed():
	department = get_department()
	created = {"masters": [], "patients": [], "clinical": [], "billing": []}

	company = COMPANY
	price_list = frappe.db.get_single_value("Selling Settings", "selling_price_list") or "Standard Selling"
	customer_group = (
		frappe.db.get_single_value("Selling Settings", "customer_group")
		or frappe.db.exists("Customer Group", "Individual")
		or "All Customer Groups"
	)

	# ── Phase 1: Masters ──────────────────────────────────────────────
	consult_item = ensure_item(
		"DEMO-OP-CONSULT",
		"DEMO OP Consultation",
		500,
		price_list,
		"Services",
		created,
	)
	cbc_item = ensure_item("DEMO-CBC-LAB", "DEMO CBC Blood Test", 300, price_list, "Services", created)
	para_item = ensure_item(
		"DEMO-PARACETAMOL",
		"DEMO Paracetamol 500mg",
		20,
		price_list,
		"Products",
		created,
		is_stock_item=1,
	)

	ensure_healthcare_settings(consult_item, created)
	appointment_type = ensure_appointment_type(consult_item, created)
	lab_template = ensure_lab_test_template(cbc_item, department, created)
	service_unit = ensure_service_unit(company, created)
	schedule = ensure_practitioner_schedule(created)
	practitioner = ensure_practitioner(consult_item, schedule, service_unit, department, created)

	# ── Phase 2: Patients ───────────────────────────────────────────
	patients = [
		ensure_patient(
			{
				"first_name": "Priya",
				"last_name": "Verma",
				"sex": "Female",
				"dob": "1995-03-15",
				"blood_group": "B Positive",
				"mobile": "9876500001",
				"email": "demo.priya@example.com",
			},
			customer_group,
			price_list,
			created,
		),
		ensure_patient(
			{
				"first_name": "Amit",
				"last_name": "Singh",
				"sex": "Male",
				"dob": "1988-07-22",
				"blood_group": "O Positive",
				"mobile": "9876500002",
				"email": "demo.amit@example.com",
			},
			customer_group,
			price_list,
			created,
		),
		ensure_patient(
			{
				"first_name": "Sneha",
				"last_name": "Patel",
				"sex": "Female",
				"dob": "2000-11-08",
				"blood_group": "A Positive",
				"mobile": "9876500003",
				"email": "demo.sneha@example.com",
			},
			customer_group,
			price_list,
			created,
		),
	]

	# ── Phase 3: OPD flow (Patient 1 — full end-to-end) ───────────────
	p1 = patients[0]
	appointment = ensure_appointment(
		p1,
		practitioner,
		appointment_type,
		service_unit,
		company,
		department,
		today(),
		"10:00:00",
		created,
	)
	vitals = ensure_vital_signs(p1, appointment, practitioner, company, created)
	encounter = ensure_encounter(p1, appointment, practitioner, lab_template, para_item, company, department, created)
	lab_test = ensure_lab_test(encounter, lab_template, company, created)
	invoice = ensure_sales_invoice(p1, company, created)

	# ── Phase 4: Scheduled appointment (Patient 2) ──────────────────
	p2 = patients[1]
	future_appt = ensure_appointment(
		p2,
		practitioner,
		appointment_type,
		service_unit,
		company,
		department,
		add_days(today(), 3),
		"11:30:00",
		created,
		status_hint="Scheduled",
	)

	# ── Phase 5: Second OPD with open encounter (Patient 3) ─────────
	p3 = patients[2]
	appt3 = ensure_appointment(
		p3,
		practitioner,
		appointment_type,
		service_unit,
		company,
		department,
		today(),
		"14:00:00",
		created,
	)
	enc3 = ensure_encounter(
		p3,
		appt3,
		practitioner,
		lab_template,
		para_item,
		company,
		department,
		created,
		submit=False,
	)

	return {
		"company": company,
		"practitioner": practitioner,
		"service_unit": service_unit,
		"lab_template": lab_template,
		"patients": [p["name"] for p in patients],
		"appointment_full_flow": appointment,
		"vital_signs": vitals,
		"encounter_submitted": encounter,
		"lab_test": lab_test,
		"sales_invoice": invoice,
		"future_appointment": future_appt,
		"draft_encounter": enc3,
		"created_log": created,
	}


# ── Helpers ───────────────────────────────────────────────────────


def get_or_create(doctype, name, values):
	if frappe.db.exists(doctype, name):
		return name
	doc = frappe.get_doc({"doctype": doctype, **values})
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_item(item_code, item_name, rate, price_list, item_group, created, is_stock_item=0):
	if not frappe.db.exists("Item Group", item_group):
		item_group = "All Item Groups"

	if frappe.db.exists("Item", item_code):
		frappe.db.set_value("Item", item_code, "is_sales_item", 1)
		return item_code

	doc = frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": item_code,
			"item_name": item_name,
			"item_group": item_group,
			"stock_uom": "Nos",
			"is_stock_item": is_stock_item,
			"is_sales_item": 1,
			"include_item_in_manufacturing": 0,
		}
	)
	doc.insert(ignore_permissions=True)

	if price_list and not frappe.db.exists(
		"Item Price", {"item_code": item_code, "price_list": price_list}
	):
		frappe.get_doc(
			{
				"doctype": "Item Price",
				"item_code": item_code,
				"price_list": price_list,
				"price_list_rate": rate,
			}
		).insert(ignore_permissions=True)

	created["masters"].append(f"Item: {item_code}")
	return item_code


def ensure_healthcare_settings(consult_item, created):
	settings = frappe.get_single("Healthcare Settings")
	changed = False
	for field, value in {
		"op_consulting_charge_item": consult_item,
		"link_customer_to_patient": 1,
		"show_payment_popup": 0,
		"process_service_request_only_if_paid": 0,
		"collect_registration_fee": 0,
		"lab_test_approval_required": 0,
	}.items():
		if settings.get(field) != value:
			settings.set(field, value)
			changed = True
	if changed:
		settings.save(ignore_permissions=True)
		created["masters"].append("Healthcare Settings updated")


def ensure_appointment_type(consult_item, created):
	name = f"{PREFIX} Consultation"
	if frappe.db.exists("Appointment Type", name):
		return name

	doc = frappe.get_doc(
		{
			"doctype": "Appointment Type",
			"appointment_type": name,
			"default_duration": 30,
			"allow_booking_for": "Practitioner",
			"color": "#29CD42",
		}
	)
	doc.append("items", {"op_consulting_charge_item": consult_item})
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"Appointment Type: {name}")
	return name


def ensure_lab_test_template(item_code, department, created):
	name = f"{PREFIX} CBC Test"
	if frappe.db.exists("Lab Test Template", name):
		return name

	lab_dept = (
		frappe.db.get_value("Medical Department", {"name": "Biochemistry"}, "name")
		or frappe.db.get_value("Medical Department", {"name": "Pathology"}, "name")
		or department
	)

	item_group = frappe.db.get_value("Item", item_code, "item_group") or "Services"
	doc = frappe.get_doc(
		{
			"doctype": "Lab Test Template",
			"lab_test_name": name,
			"lab_test_code": item_code,
			"link_existing_item": 1,
			"item": item_code,
			"lab_test_group": item_group,
			"department": lab_dept,
			"is_billable": 1,
			"lab_test_rate": 300,
			"lab_test_template_type": "Single",
			"lab_test_description": "Complete Blood Count — demo test",
		}
	)
	doc.append(
		"normal_test_templates",
		{
			"lab_test_event": "Haemoglobin",
			"lab_test_uom": "g / L",
			"normal_range": "12 - 16",
			"require_result_value": 1,
		},
	)
	doc.append(
		"normal_test_templates",
		{
			"lab_test_event": "WBC Count",
			"lab_test_uom": "cells / cumm",
			"normal_range": "4000 - 11000",
			"require_result_value": 1,
		},
	)
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"Lab Test Template: {name}")
	return name


def ensure_service_unit(company, created):
	su_type = f"{PREFIX} OPD Room Type"
	if not frappe.db.exists("Healthcare Service Unit Type", su_type):
		frappe.get_doc(
			{
				"doctype": "Healthcare Service Unit Type",
				"service_unit_type": su_type,
				"allow_appointments": 1,
			}
		).insert(ignore_permissions=True)
		created["masters"].append(f"Service Unit Type: {su_type}")

	root = frappe.db.get_value(
		"Healthcare Service Unit",
		{"company": company, "parent_healthcare_service_unit": ["is", "not set"]},
		"name",
	)
	if not root:
		root = f"All Healthcare Service Units - {company[:2].upper()}"
		if not frappe.db.exists("Healthcare Service Unit", root):
			frappe.get_doc(
				{
					"doctype": "Healthcare Service Unit",
					"healthcare_service_unit_name": f"All Healthcare Service Units - {company}",
					"is_group": 1,
					"company": company,
				}
			).insert(ignore_permissions=True)

	su_name = f"{PREFIX} OPD Room 1"
	abbr = frappe.get_cached_value("Company", company, "abbr")
	full_name = f"{su_name} - {abbr}"
	if frappe.db.exists("Healthcare Service Unit", full_name):
		return full_name

	doc = frappe.get_doc(
		{
			"doctype": "Healthcare Service Unit",
			"healthcare_service_unit_name": su_name,
			"is_group": 0,
			"parent_healthcare_service_unit": root,
			"service_unit_type": su_type,
			"allow_appointments": 1,
			"overlap_appointments": 0,
			"service_unit_capacity": 3,
			"company": company,
		}
	)
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"Service Unit: {doc.name}")
	return doc.name


def ensure_practitioner_schedule(created):
	name = f"{PREFIX} Weekday Schedule"
	if frappe.db.exists("Practitioner Schedule", name):
		return name

	weekday = getdate(today()).strftime("%A")
	doc = frappe.get_doc(
		{
			"doctype": "Practitioner Schedule",
			"schedule_name": name,
		}
	)
	doc.append(
		"time_slots",
		{
			"day": weekday,
			"from_time": "09:00:00",
			"to_time": "17:00:00",
			"duration": 30,
			"maximum_appointments": 16,
		},
	)
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"Practitioner Schedule: {name}")
	return name


def ensure_practitioner(consult_item, schedule, service_unit, department, created):
	existing = frappe.db.get_value(
		"Healthcare Practitioner",
		{"first_name": "Ananya", "last_name": "Rao"},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Healthcare Practitioner",
			"naming_series": "HLC-PRAC-.YYYY.-",
			"first_name": "Ananya",
			"last_name": "Rao",
			"gender": "Female",
			"practitioner_type": "Internal",
			"department": department,
			"status": "Active",
			"mobile_phone": "9876511111",
			"op_consulting_charge_item": consult_item,
			"op_consulting_charge": 500,
		}
	)
	doc.append("practitioner_schedules", {"schedule": schedule, "service_unit": service_unit})
	doc.insert(ignore_permissions=True)
	created["masters"].append(f"Practitioner: {doc.name}")
	return doc.name


def ensure_patient(data, customer_group, price_list, created):
	full_name = f"{data['first_name']} {data['last_name']}"
	marker = f"{PREFIX} {full_name}"
	existing = frappe.db.get_value("Patient", {"first_name": data["first_name"], "last_name": data["last_name"]})
	if existing:
		return {"name": existing, "patient_name": full_name}

	doc = frappe.get_doc(
		{
			"doctype": "Patient",
			"naming_series": "HLC-PAT-.YYYY.-",
			"first_name": data["first_name"],
			"last_name": data["last_name"],
			"sex": data["sex"],
			"dob": data["dob"],
			"blood_group": data.get("blood_group"),
			"mobile": data.get("mobile"),
			"email": data.get("email"),
			"status": "Active",
			"invite_user": 0,
			"customer_group": customer_group,
			"default_price_list": price_list,
			"occupation": "Demo patient",
			"marital_status": "Single",
		}
	)
	doc.insert(ignore_permissions=True)
	created["patients"].append(f"Patient: {doc.name} ({marker})")
	return {"name": doc.name, "patient_name": doc.patient_name}


def ensure_appointment(
	patient,
	practitioner,
	appointment_type,
	service_unit,
	company,
	department,
	appt_date,
	appt_time,
	created,
	status_hint=None,
):
	key = f"{patient['name']}-{appt_date}-{appt_time}"
	existing = frappe.db.exists(
		"Patient Appointment",
		{
			"patient": patient["name"],
			"appointment_date": appt_date,
			"appointment_time": appt_time,
		},
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Patient Appointment",
			"naming_series": "HLC-APP-.YYYY.-",
			"appointment_type": appointment_type,
			"appointment_for": "Practitioner",
			"company": company,
			"practitioner": practitioner,
			"department": department,
			"service_unit": service_unit,
			"patient": patient["name"],
			"appointment_date": appt_date,
			"appointment_time": appt_time,
			"duration": 30,
			"notes": f"{PREFIX} demo appointment",
		}
	)
	if status_hint:
		doc.status = status_hint
	doc.insert(ignore_permissions=True)
	created["clinical"].append(f"Appointment: {doc.name} ({patient['patient_name']})")
	return doc.name


def ensure_vital_signs(patient, appointment, practitioner, company, created):
	existing = frappe.db.exists("Vital Signs", {"patient": patient["name"], "appointment": appointment})
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Vital Signs",
			"naming_series": "HLC-VS-.YYYY.-",
			"patient": patient["name"],
			"appointment": appointment,
			"company": company,
			"signs_date": today(),
			"signs_time": now_datetime().strftime("%H:%M:%S"),
			"temperature": 98.6,
			"pulse": 78,
			"respiratory_rate": 18,
			"bp_systolic": 120,
			"bp_diastolic": 80,
			"height": 165,
			"weight": 58,
			"vital_signs_note": f"{PREFIX} vitals recorded before consultation",
		}
	)
	doc.insert(ignore_permissions=True)
	created["clinical"].append(f"Vital Signs: {doc.name}")
	return doc.name


def ensure_complaint(text, created):
	if frappe.db.exists("Complaint", text):
		return text
	frappe.get_doc({"doctype": "Complaint", "complaints": text}).insert(ignore_permissions=True)
	created["masters"].append(f"Complaint: {text}")
	return text


def ensure_diagnosis(text, created):
	if frappe.db.exists("Diagnosis", text):
		return text
	frappe.get_doc({"doctype": "Diagnosis", "diagnosis": text}).insert(ignore_permissions=True)
	created["masters"].append(f"Diagnosis: {text}")
	return text


def ensure_encounter(
	patient,
	appointment,
	practitioner,
	lab_template,
	drug_item,
	company,
	department,
	created,
	submit=True,
):
	existing = frappe.db.exists("Patient Encounter", {"appointment": appointment})
	if existing:
		doc = frappe.get_doc("Patient Encounter", existing)
		if submit and doc.docstatus == 0:
			doc.submit()
		return doc.name

	complaint = ensure_complaint("Fever and body ache", created)
	diagnosis = ensure_diagnosis("Viral fever", created)

	doc = frappe.get_doc(
		{
			"doctype": "Patient Encounter",
			"naming_series": "HLC-ENC-.YYYY.-",
			"appointment": appointment,
			"patient": patient["name"],
			"practitioner": practitioner,
			"medical_department": department,
			"company": company,
			"encounter_date": today(),
			"encounter_time": now_datetime().strftime("%H:%M:%S"),
		}
	)
	doc.append("symptoms", {"complaint": complaint})
	doc.append("diagnosis", {"diagnosis": diagnosis})
	doc.append(
		"lab_test_prescription",
		{
			"lab_test_code": lab_template,
			"lab_test_comment": f"{PREFIX} CBC ordered",
		},
	)
	dosage = frappe.db.get_value("Prescription Dosage", {}, "name") or "BID"
	period = frappe.db.get_value("Prescription Duration", {}, "name")
	if period:
		doc.append(
			"drug_prescription",
			{
				"drug_code": drug_item,
				"dosage": dosage,
				"period": period,
				"dosage_form": "Tablet",
				"comment": f"{PREFIX} take after food",
			},
		)
	doc.insert(ignore_permissions=True)
	created["clinical"].append(
		f"Patient Encounter: {doc.name} ({'submitted' if submit else 'draft'})"
	)
	if submit:
		frappe.flags.in_test = True
		try:
			doc.submit()
		finally:
			frappe.flags.in_test = False
	return doc.name


def ensure_lab_test(encounter_name, lab_template, company, created):
	encounter = frappe.get_doc("Patient Encounter", encounter_name)
	service_request = frappe.db.get_value(
		"Service Request",
		{"order_group": encounter_name, "template_dn": lab_template},
		"name",
	)
	if not service_request:
		frappe.throw(f"No Service Request found for encounter {encounter_name}")

	existing = frappe.db.exists("Lab Test", {"service_request": service_request})
	if existing:
		doc = frappe.get_doc("Lab Test", existing)
		if doc.docstatus == 0:
			_fill_lab_results(doc)
			frappe.flags.in_test = True
			try:
				doc.submit()
			finally:
				frappe.flags.in_test = False
		return doc.name

	from healthcare.healthcare.doctype.service_request.service_request import make_lab_test

	lab_test = make_lab_test(frappe.get_doc("Service Request", service_request))
	lab_test.company = company
	lab_test.insert(ignore_permissions=True)
	_fill_lab_results(lab_test)
	frappe.flags.in_test = True
	try:
		lab_test.submit()
	finally:
		frappe.flags.in_test = False
	created["clinical"].append(f"Lab Test: {lab_test.name} (submitted with results)")
	return lab_test.name


def _fill_lab_results(lab_test):
	for row in lab_test.normal_test_items or []:
		if "Haemoglobin" in (row.lab_test_name or row.lab_test_event or ""):
			row.result_value = "14.2"
		elif "WBC" in (row.lab_test_name or row.lab_test_event or ""):
			row.result_value = "7500"
		else:
			row.result_value = row.result_value or "Normal"
	lab_test.save(ignore_permissions=True)


def ensure_sales_invoice(patient, company, created):
	patient_name = patient["name"]
	customer = frappe.db.get_value("Patient", patient_name, "customer")
	if not customer:
		frappe.throw(f"Patient {patient_name} has no linked Customer")

	existing = frappe.db.get_value(
		"Sales Invoice",
		{"patient": patient_name, "company": company, "docstatus": 1},
		"name",
	)
	if existing:
		return existing

	from healthcare.healthcare.utils import get_healthcare_services_to_invoice

	services = get_healthcare_services_to_invoice(patient_name, customer, company) or []
	if not services:
		frappe.throw("No billable healthcare services found for demo patient")

	invoice = frappe.new_doc("Sales Invoice")
	invoice.customer = customer
	invoice.patient = patient_name
	invoice.company = company
	invoice.posting_date = today()
	invoice.due_date = today()

	checked = []
	for svc in services:
		checked.append(
			{
				"item": svc.get("service"),
				"dn": svc.get("reference_name"),
				"dt": svc.get("reference_type"),
				"rate": svc.get("rate"),
				"qty": svc.get("qty") or 1,
				"income_account": svc.get("income_account"),
				"description": "",
			}
		)

	invoice.set_healthcare_services(checked)
	invoice.insert(ignore_permissions=True)
	frappe.flags.in_test = True
	try:
		invoice.submit()
	finally:
		frappe.flags.in_test = False
	created["billing"].append(f"Sales Invoice: {invoice.name}")
	return invoice.name


def print_summary(result):
	print("\n" + "=" * 60)
	print("HEALTHCARE DEMO DATA CREATED")
	print("=" * 60)
	print(f"Company          : {result['company']}")
	print(f"Practitioner     : {result['practitioner']}")
	print(f"Service Unit     : {result['service_unit']}")
	print(f"Lab Template     : {result['lab_template']}")
	print()
	print("Patients:")
	for p in result["patients"]:
		print(f"  - {p}")
	print()
	print("End-to-end flow (Patient 1):")
	print(f"  Appointment  → {result['appointment_full_flow']}")
	print(f"  Vital Signs  → {result['vital_signs']}")
	print(f"  Encounter    → {result['encounter_submitted']}")
	print(f"  Lab Test     → {result['lab_test']}")
	print(f"  Sales Invoice→ {result['sales_invoice']}")
	print()
	print("Other records:")
	print(f"  Future Appointment (Patient 2) → {result['future_appointment']}")
	print(f"  Draft Encounter (Patient 3)    → {result['draft_encounter']}")
	print()
	print("Open in desk:")
	print("  /app/patient")
	print("  /app/patient-appointment")
	print("  /app/patient-encounter")
	print("  /app/lab-test")
	print("  /app/service-request")
	print("  /app/sales-invoice")
	print("=" * 60)
