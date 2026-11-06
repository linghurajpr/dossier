from __future__ import annotations

import json
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent
CASES = ROOT / "cases"
GROUND_TRUTH = ROOT / "ground_truth"
MONTHS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet",
          "août", "septembre", "octobre", "novembre", "décembre")


def iban_checksum(bban: str) -> str:
    """Return the two check digits for a French IBAN BBAN."""
    rearranged = f"{bban}FR00"
    numeric = "".join(str(int(char, 36)) if char.isalpha() else char for char in rearranged)
    return f"{98 - (int(numeric) % 97):02d}"


def make_iban(account_digits: str) -> str:
    bban = f"00000{account_digits[:5]:0>5}{account_digits[5:16]:0>11}00"
    return f"FR{iban_checksum(bban)}{bban}"


def iban_passes_mod97(iban: str) -> bool:
    rearranged = iban[4:] + iban[:4]
    numeric = "".join(str(int(char, 36)) if char.isalpha() else char for char in rearranged)
    return int(numeric) % 97 == 1


def french_date(value: str, words: bool = False) -> str:
    year, month, day = map(int, value.split("-"))
    return f"{day} {MONTHS[month - 1]} {year}" if words else f"{day:02d}/{month:02d}/{year}"


def page_start(pdf: canvas.Canvas, title: str, rotated: bool = False) -> None:
    width, height = A4
    pdf.saveState()
    pdf.setFillColorRGB(0.86, 0.86, 0.86)
    pdf.setFont("Helvetica-Bold", 27)
    pdf.translate(width / 2, height / 2)
    pdf.rotate(35)
    pdf.drawCentredString(0, 0, "SPECIMEN - DONNEES FICTIVES")
    pdf.restoreState()
    pdf.setFillColorRGB(0.12, 0.17, 0.23)
    pdf.setFont("Helvetica-Bold", 17)
    pdf.drawString(54, height - 58, title)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(54, height - 76, "Document de démonstration — données inventées")
    pdf.setStrokeColorRGB(0.55, 0.58, 0.61)
    pdf.line(54, 42, width - 54, 42)
    pdf.setFillColorRGB(0.3, 0.3, 0.3)
    pdf.setFont("Helvetica", 8)
    pdf.drawCentredString(width / 2, 28, "Synthetic test data")
    if rotated:
        pdf.saveState()
        pdf.translate(width / 2, height / 2)
        pdf.rotate(1.7)
        pdf.translate(-width / 2, -height / 2)


def page_end(pdf: canvas.Canvas, rotated: bool = False) -> None:
    if rotated:
        pdf.restoreState()
    pdf.showPage()


def line(pdf: canvas.Canvas, label: str, value: str, y: int, x: int = 58) -> None:
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x, y, label)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(x + 135, y, value)


def column_field(pdf: canvas.Canvas, x: int, y: int, label: str, value: str) -> None:
    pdf.setFillColorRGB(0.12, 0.17, 0.23)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x, y, label)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(x, y - 17, value)


def table(pdf: canvas.Canvas, rows: list[tuple[str, str]], x: int, y: int,
          widths: tuple[int, int] = (170, 300), row_height: int = 29) -> None:
    pdf.setFont("Helvetica-Bold", 9)
    for label, value in rows:
        pdf.setFillColorRGB(0.91, 0.93, 0.95)
        pdf.rect(x, y - 6, widths[0] + widths[1], row_height, fill=1, stroke=0)
        pdf.setFillColorRGB(0.12, 0.17, 0.23)
        pdf.drawString(x + 8, y + 5, label)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(x + widths[0] + 8, y + 5, value)
        pdf.setFont("Helvetica-Bold", 9)
        y -= row_height


def make_lease(path: Path, fields: dict, rotated: bool = False) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    page_start(pdf, "Contrat de location — habitation", rotated)
    pdf.setFont("Helvetica", 10)
    pdf.drawString(58, 690, "Entre les soussignés, pour le logement désigné ci-dessous :")
    line(pdf, "Bailleur :", fields["landlord_name"], 655)
    line(pdf, "Locataire :", fields["tenant_name"], 628)
    line(pdf, "Adresse du bien :", fields["property_address"], 584)
    line(pdf, "Loyer mensuel :", f"{fields['monthly_rent_eur']} EUR", 540)
    line(pdf, "Charges :", f"{fields['charges_eur']} EUR", 513)
    line(pdf, "Prise d'effet :", french_date(fields["lease_start"]), 469)
    line(pdf, "Fin du bail :", french_date(fields["lease_end"], True), 442)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(58, 380, "Le présent document est établi à titre de jeu de données synthétique.")
    page_end(pdf, rotated)
    pdf.save()


def make_rib(path: Path, fields: dict) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    page_start(pdf, "Relevé d'identité bancaire")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(58, 690, "Coordonnées de compte — organisme fictif")
    table(pdf, [
        ("Titulaire du compte", fields["account_holder"]),
        ("Adresse du titulaire", fields["holder_address"]),
        ("IBAN", fields["iban"]),
        ("BIC", fields["bic"]),
        ("Établissement", fields["bank_name"]),
    ], 58, 640, widths=(170, 360), row_height=34)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(58, 425, "Aucun établissement réel n'est représenté.")
    page_end(pdf)
    pdf.save()


def make_enrollment(path: Path, fields: dict) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    page_start(pdf, "Certificat de scolarité")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(58, 690, "L'établissement certifie l'inscription de l'étudiant(e) :")
    pdf.setStrokeColorRGB(0.6, 0.62, 0.65)
    pdf.line(300, 240, 300, 660)
    column_field(pdf, 62, 635, "Nom de l'étudiant(e)", fields["student_name"])
    column_field(pdf, 62, 575, "Date de naissance", french_date(fields["date_of_birth"]))
    column_field(pdf, 315, 635, "Université", fields["university"])
    column_field(pdf, 315, 575, "Formation", fields["program"])
    column_field(pdf, 315, 515, "Année universitaire", fields["academic_year"])
    column_field(pdf, 315, 455, "Statut d'inscription", fields["enrollment_status"])
    pdf.setFont("Helvetica", 9)
    pdf.drawString(315, 480, "Inscription administrative")
    pdf.drawString(315, 460, "validée pour l'année indiquée.")
    page_end(pdf)
    pdf.save()


def make_permit(path: Path, fields: dict, rotated: bool = False) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    page_start(pdf, "Attestation de séjour — spécimen", rotated)
    line(pdf, "Titulaire :", fields["holder_name"], 650)
    line(pdf, "Nationalité :", fields["nationality"], 615)
    line(pdf, "Type de titre :", fields["permit_type"], 570)
    line(pdf, "Valide du :", french_date(fields["valid_from"], True), 525)
    line(pdf, "Valide jusqu'au :", french_date(fields["valid_until"]), 490)
    pdf.setFont("Helvetica", 9)
    pdf.drawString(58, 420, "Document fictif sans valeur administrative.")
    page_end(pdf, rotated)
    pdf.save()


def case_fields(case_id: str) -> dict:
    name = "Éloïse Martin" if case_id == "case_c" else "Camille Durand"
    rib_name = "ELOISE MARTIN" if case_id == "case_c" else name
    lease_address = "12 rue des Lilas 75011 Paris"
    rib_address = ("48 avenue Jean Jaures 69007 Lyon" if case_id == "case_a"
                   else lease_address)
    return {
        "lease": {
            "tenant_name": name, "landlord_name": "Société Civile Exemple",
            "property_address": lease_address, "monthly_rent_eur": 850,
            "charges_eur": 75, "lease_start": "2026-09-12", "lease_end": "2027-09-11",
        },
        "rib": {
            "account_holder": rib_name, "holder_address": rib_address,
            "iban": make_iban("123456789012345" if case_id == "case_a"
                              else "543210987654321"),
            "bic": "FICTFRPPXXX",
            "bank_name": "Banque Exemple",
        },
        "enrollment": {
            "student_name": name, "date_of_birth": "2004-03-08",
            "university": "Université des Rives (fictive)",
            "program": "Licence de lettres", "academic_year": "2026-2027",
            "enrollment_status": "Inscription validée",
        },
        "permit": {
            "holder_name": name, "nationality": "Française",
            "permit_type": "Attestation fictive de résidence",
            "valid_from": "2026-09-12", "valid_until": "2027-09-11",
        },
    }


def generate_case(case_id: str) -> None:
    fields = case_fields(case_id)
    case_dir = CASES / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    for section in fields.values():
        if "iban" in section and not iban_passes_mod97(section["iban"]):
            raise ValueError(f"Generated IBAN failed mod-97: {section['iban']}")
    make_lease(case_dir / "lease.pdf", fields["lease"], rotated=case_id == "case_a")
    make_rib(case_dir / "rib.pdf", fields["rib"])
    make_enrollment(case_dir / "enrollment.pdf", fields["enrollment"])
    make_permit(case_dir / "permit.pdf", fields["permit"])
    expected = ([{"rule": "ADDRESS_MISMATCH", "severity": "error"}]
                if case_id == "case_a" else [])
    truth = {
        "case_id": case_id, "fields": fields, "expected_findings": expected,
        "must_not_flag": ["NAME_MISMATCH"] if case_id == "case_c" else [],
    }
    GROUND_TRUTH.mkdir(parents=True, exist_ok=True)
    (GROUND_TRUTH / f"{case_id}.json").write_text(
        json.dumps(truth, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def main() -> None:
    for case_id in ("case_a", "case_c"):
        generate_case(case_id)
    print("Generated two synthetic document cases.")


if __name__ == "__main__":
    main()
