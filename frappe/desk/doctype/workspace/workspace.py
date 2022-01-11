# -*- coding: utf-8 -*-
# Copyright (c) 2020, Frappe Technologies and contributors
# License: MIT. See LICENSE

import frappe
from frappe import _
from frappe.modules.export_file import export_to_files
from frappe.model.document import Document
from frappe.desk.desktop import save_new_widget
from frappe.desk.utils import validate_route_conflict

from json import loads

class Workspace(Document):
	def validate(self):
		if (self.public and not is_workspace_manager() and not disable_saving_as_public()):
			frappe.throw(_("You need to be Workspace Manager to edit this document"))
		validate_route_conflict(self.doctype, self.name)

		try:
			if not isinstance(loads(self.content), list):
				raise
		except Exception:
			frappe.throw(_("Content data shoud be a list"))

	def on_update(self):
		if disable_saving_as_public():
			return

		if frappe.conf.developer_mode and self.module and self.public:
			export_to_files(record_list=[['Workspace', self.name]], record_module=self.module)

	@staticmethod
	def get_module_page_map():
		pages = frappe.get_all("Workspace", fields=["name", "module"], filters={'for_user': ''}, as_list=1)

		return { page[1]: page[0] for page in pages if page[1] }

	def get_link_groups(self):
		cards = []
		current_card = frappe._dict({
			"label": "Link",
			"type": "Card Break",
			"icon": None,
			"hidden": False,
		})

		card_links = []

		for link in self.links:
			link = link.as_dict()
			if link.type == "Card Break":
				if card_links and (not current_card.get('only_for') or current_card.get('only_for') == frappe.get_system_settings('country')):
					current_card['links'] = card_links
					cards.append(current_card)

				current_card = link
				card_links = []
			else:
				card_links.append(link)

		current_card['links'] = card_links
		cards.append(current_card)

		return cards

	def build_links_table_from_card(self, config):

		for idx, card in enumerate(config):
			links = loads(card.get('links'))

			# remove duplicate before adding
			for idx, link in enumerate(self.links):
				if link.label == card.get('label') and link.type == 'Card Break':
					del self.links[idx : idx + link.link_count + 1]

			self.append('links', {
				"label": card.get('label'),
				"type": "Card Break",
				"icon": card.get('icon'),
				"hidden": card.get('hidden') or False,
				"link_count": card.get('link_count'),
				"idx": 1 if not self.links else self.links[-1].idx + 1
			})

			for link in links:
				self.append('links', {
					"label": link.get('label'),
					"type": "Link",
					"link_type": link.get('link_type'),
					"link_to": link.get('link_to'),
					"onboard": link.get('onboard'),
					"only_for": link.get('only_for'),
					"dependencies": link.get('dependencies'),
					"is_query_report": link.get('is_query_report'),
					"idx": self.links[-1].idx + 1
				})

def disable_saving_as_public():
	return frappe.flags.in_install or \
			frappe.flags.in_patch or \
			frappe.flags.in_test or \
			frappe.flags.in_fixtures or \
			frappe.flags.in_migrate

def get_link_type(key):
	key = key.lower()

	link_type_map = {
		"doctype": "DocType",
		"page": "Page",
		"report": "Report"
	}

	if key in link_type_map:
		return link_type_map[key]

	return "DocType"

def get_report_type(report):
	report_type = frappe.get_value("Report", report, "report_type")
	return report_type in ["Query Report", "Script Report", "Custom Report"]


@frappe.whitelist()
def save_page(title, icon, parent, public, sb_public_items, sb_private_items, deleted_pages, new_widgets, blocks, save):
	save = frappe.parse_json(save)
	public = frappe.parse_json(public)
	if save:
		doc = frappe.new_doc('Workspace')
		doc.title = title
		doc.icon = icon
		doc.content = blocks
		doc.parent_page = parent

		if public:
			doc.label = title
			doc.public = 1
		else:
			doc.label = title + "-" + frappe.session.user
			doc.for_user = frappe.session.user
		doc.save(ignore_permissions=True)
	else:
		if public:
			filters = {
				'public': public,
				'label': title
			}
		else:
			filters = {
				'for_user': frappe.session.user,
				'label': title + "-" + frappe.session.user
			}
		pages = frappe.get_list("Workspace", filters=filters)
		if pages:
			doc = frappe.get_doc("Workspace", pages[0])

		doc.content = blocks
		doc.save(ignore_permissions=True)

	if loads(new_widgets):
		save_new_widget(doc, title, blocks, new_widgets)

	if loads(sb_public_items) or loads(sb_private_items):
		sort_pages(loads(sb_public_items), loads(sb_private_items))

	if loads(deleted_pages):
		return delete_pages(loads(deleted_pages))

	return {"name": title, "public": public, "label": doc.label}

def delete_pages(deleted_pages):
	for page in deleted_pages:
		if page.get("public") and not is_workspace_manager():
			return {"name": page.get("title"), "public": 1, "label": page.get("label")}

		if frappe.db.exists("Workspace", page.get("name")):
			frappe.get_doc("Workspace", page.get("name")).delete(ignore_permissions=True)

	return {"name": "Home", "public": 1, "label": "Home"}

def sort_pages(sb_public_items, sb_private_items):
	wspace_public_pages = get_page_list(['name', 'title'], {'public': 1})
	wspace_private_pages = get_page_list(['name', 'title'], {'for_user': frappe.session.user})

	if sb_private_items:
		sort_page(wspace_private_pages, sb_private_items)

	if sb_public_items and is_workspace_manager():
		sort_page(wspace_public_pages, sb_public_items)

def sort_page(wspace_pages, pages):
	for seq, d in enumerate(pages):
		for page in wspace_pages:
			if page.title == d.get('title'):
				doc = frappe.get_doc('Workspace', page.name)
				doc.sequence_id = seq + 1
				doc.parent_page = d.get('parent_page') or ""
				doc.save(ignore_permissions=True)
				break

def get_page_list(fields, filters):
	return frappe.get_list("Workspace", fields=fields, filters=filters, order_by='sequence_id asc')

def is_workspace_manager():
	return "Workspace Manager" in frappe.get_roles()
