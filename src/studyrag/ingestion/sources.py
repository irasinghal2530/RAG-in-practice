"""
Catalog of every public source the Electric Motor Copilot is built from
(induction motors + drives, Indian manufacturing focus).

Each category maps to (filename, url, licence/usage note). The note is carried through
to every chunk, so downstream answers can cite the source and respect its licence.
"""

import re

WAYBACK = "https://web.archive.org/web/2023id_/"  # id_ = raw archived bytes, no toolbar

# (filename, url, licence/usage note)
SOURCES = {
    # ---- 1. Motor OEM manuals: troubleshooting tables, maintenance schedules, lubrication
    "manuals": [
        ("abb_lv_motors_iom_2009.pdf",
         "https://library.e.abb.com/public/e20ddd6a89ed4815821e8163f569bf63/Standard_LV_Motors_Manual_EN_01_2009%20Rev%20D.pdf",
         "ABB copyright - use locally, do not redistribute"),
        ("abb_ex_motors_iom_2007.pdf",
         "https://library.e.abb.com/public/90e58f5525c91b8dc1257dd90033e090/Ex%20Motor%20Manual%20EN%202007_01_01.pdf",
         "ABB copyright - has a motor troubleshooting chart"),
        ("weg_t_line_induction_motor_iom.pdf",
         "https://static.weg.net/medias/downloadcenter/hf2/h8f/WEG-three-phase-induction-motors-t-line-squirrel-cage-rotor-12364818-manual-english-dc.pdf",
         "WEG permits reproduction with attribution (see manual notes)"),
        ("weg_general_electric_motor_iom.pdf",
         "https://www.wolfautomation.com/content/weg-electricmotor-installman-21.pdf",
         "WEG copyright - IEC 56-630 / NEMA 42-9606 frames, LV + HV, hosted by a distributor"),
        ("toshiba_lv_induction_motor_iom.pdf",
         "https://cdn.automationdirect.com/static/manuals/toshibamotors/umwtoshibamotors.pdf",
         "Toshiba copyright - troubleshooting + testing section"),
        ("siemens_horizontal_induction_motor_iom.pdf",
         WAYBACK + "https://assets.new.siemens.com/siemens/assets/api/uuid:02e1582d-2bc4-4aad-bd35-b45c07ae05dd/horiz-tefc-teao-anim03522-ed07.pdf",
         "Siemens copyright - includes vibration analysis sheet (Wayback copy)"),
        ("hyosung_nema_lv_motor_om.pdf",
         "https://www.hyosungheavyindustries.com/resources/files/nema/NEMA_LV_motor_O_M_manual_EN.pdf",
         "Hyosung copyright"),
        ("baldor_mn431_iom.pdf",
         "https://www.baldor.com/mvc/DownloadCenter/Files/MN431",
         "Baldor/ABB copyright - maintenance & troubleshooting chapter"),
        ("brook_crompton_td103_maintenance.pdf",
         "https://tte-lisa.ac.uk/wp-content/uploads/vle_content/Phase2/electrical/CAROUSEL3/Resource/Motor%20Maintenance%20Manual%20TD103-4E.pdf",
         "Brook Crompton copyright - installation & maintenance of AC induction motors"),
    ],
    # ---- 2. VFD / drive manuals: fault codes, alarms, motor-drive interaction
    "drives": [
        ("abb_acs580_firmware_manual.pdf",
         "https://www.ghv.de/files/elektrische-antriebstechnik/frequenzumrichter/acs580/downloads/dokumentationen/en_acs580_firmware_ghv.pdf",
         "ABB copyright - fault tracing chapter (3AXD50000016097), distributor copy"),
        ("siemens_g120_cu240be2_operating_instructions.pdf",
         "https://cache.industry.siemens.com/dl/files/562/94020562/att_75518/v1/G120_CU240BE2_BA6_0414_eng.pdf",
         "Siemens copyright - alarms, faults and system messages chapter"),
    ],
    # ---- 3. Indian standards (BIS) - the codes Indian plants are audited against
    "standards": [
        ("is_900_1992_induction_motor_installation_maintenance.pdf",
         "https://law.resource.org/pub/in/bis/S05/is.900.1992.pdf",
         "BIS IS 900 - code of practice for installation & maintenance of induction motors"),
        ("is_325_1996_three_phase_induction_motors.pdf",
         "https://law.resource.org/pub/in/bis/S05/is.325.1996.pdf",
         "BIS IS 325 - three-phase induction motors specification"),
        ("is_12615_2011_energy_efficient_motors.pdf",
         "https://law.resource.org/pub/in/bis/S05/is.12615.2011.pdf",
         "BIS IS 12615 - energy efficient induction motors (IE classes)"),
    ],
    # ---- 4. Knowledge/guide books: the "why" behind troubleshooting + efficiency
    "guides": [
        ("doe_motor_drive_sourcebook.pdf",
         "https://www.energy.gov/sites/prod/files/2014/04/f15/amo_motors_sourcebook_web.pdf",
         "US Government work - public domain; 2014 3rd edition"),
        ("doe_motor_drive_sourcebook_2008_tip_sheets.pdf",
         "https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/motor.pdf",
         "US Government work - public domain; older edition, Appendix B = motor tip sheets"),
        ("doe_premium_efficiency_motor_handbook.pdf",
         "https://www.energy.gov/sites/prod/files/2014/04/f15/amo_motors_handbook_web.pdf",
         "US Government work - public domain; selection, rewind, efficiency evaluation"),
        ("doe_determining_motor_load_and_efficiency.pdf",
         "https://www.energy.gov/sites/prod/files/2014/04/f15/10097517.pdf",
         "US Government work - public domain; kW / slip / amperage load methods"),
        ("iea_4e_emsa_motor_system_audit_guide.pdf",
         "https://www.iea-4e.org/wp-content/uploads/publications/2018/03/emsa_audit_guide_apr2018.pdf",
         "IEA 4E EMSA - ISO 50002-based audit steps for motor-driven systems"),
        ("unep_energy_efficiency_guide_industry_asia.pdf",
         "https://digitallibrary.un.org/record/721301/files/-Energy%2520Efficiency%2520Guide%2520for%2520Industry%2520in%2520Asia-2006634.pdf",
         "UNEP 2006 - equipment chapters incl. electric motors, Asian case studies"),
        ("easa_aemt_rewind_study.pdf",
         "https://iecex.com/dmsdocument/1577",
         "EASA/AEMT - effect of repair/rewinding on motor efficiency"),
        ("bee_book3_checklists_tips.pdf",
         "https://www.beeindia.gov.in/sites/default/files/3ChAnnexure.pdf",
         "BEE (Govt of India) - energy-saving checklists incl. motors"),
    ],
    # ---- 5. Indian factory energy audit reports
    # beeindia.gov.in was rebuilt and every /sites/default/files/ link now redirects to
    # the homepage. Only Jodhpur survives intact on the Wayback Machine. The per-unit BEA reports
    # (Hira, Patel, JP Hansraj, SR Pulses, Rama Agro, Nanak Overseas, Global Exports,
    # Mehram, Khalon, Shree Padmawati, NN Products, Bharat International, Saggu Toka)
    # were never archived - see https://beeindia.gov.in/en/baseline-energy-audit-reports
    "bee_audits": [
        (f"{name.lower().replace(' ', '_')}.pdf",
         f"https://web.archive.org/web/{ts}id_/https://beeindia.gov.in/sites/default/files/{path}",
         "BEE (Govt of India) public report - redact PII (PAN, bank details) at ingestion")
        for name, ts, path in [
            ("Jodhpur Limestone Cluster Manual", "20210514142653", "Jodhpur_Limestone_CII.pdf"),
            # the 35-cluster situation analysis is archived too, but the capture is truncated at 1 MB
        ]
    ],
    # ---- 6. Structured maintenance history (synthetic but realistic schema)
    # The original Azure blob (azuremlsampleexperiments) is gone; this GitHub repo mirrors it.
    "maintenance_logs": [
        (f"azure_pdm_{t}.csv",
         "https://raw.githubusercontent.com/ashishpatel26/Predictive_Maintenance_using_"
         f"Machine-Learning_Microsoft_Casestudy/master/data/PdM_{t}.csv",
         "Microsoft sample data (synthetic) - 100 machines, voltage/rotation/vibration, 2015")
        for t in ["telemetry", "errors", "maint", "failures", "machines"]
    ],
    # ---- 7. Papers / programme overviews: fault physics and dataset descriptions
    "papers": [
        ("bearing_fault_ml_dl_review_arxiv_1901.08247.pdf",
         "https://arxiv.org/pdf/1901.08247",
         "arXiv - Zhang et al., ML/DL for bearing fault diagnostics review (covers CWRU)"),
        ("mafaulda_cwru_kan_arxiv_2412.01322.pdf",
         "https://arxiv.org/pdf/2412.01322",
         "arXiv - fault/severity classification on CWRU + MaFaulDa (dataset descriptions)"),
        ("rotating_machinery_dl_benchmark_arxiv_2003.03315.pdf",
         "https://arxiv.org/pdf/2003.03315",
         "arXiv - Zhao et al., open-source benchmark over CWRU, Paderborn, MFPT, etc."),
        ("multi_fault_rotating_machines_review_arxiv_2206.14153.pdf",
         "https://arxiv.org/pdf/2206.14153",
         "arXiv - two decades of multi-fault diagnosis research on rotating machines"),
        ("broken_rotor_bar_mcsa_survey.pdf",
         "https://ecce-journals.rtu.lv/ecce/article/download/ecce-2018-0014/188/206",
         "ECCE 2018 open access - broken rotor bar diagnosis, MCSA, fault taxonomy table"),
        ("bee_sme_programme_overview.pdf",
         "https://sameeeksha.org/pdf/presentation/Energy-Efficiency-Programs-for-SMEs_BEE.pdf",
         "BEE presentation on the SME energy efficiency programme"),
        ("bee_foundry_cluster_ecm_manual.pdf",
         "https://www.beeindia.gov.in/WriteReadData/RTF1984/RTF-PDF-646558505c8e64b3_1776139721.pdf",
         "BEE/CII - energy conservation measures, Batala/Jalandhar/Ludhiana foundry clusters"),
    ],
}

# CWRU bearing data: motor drive-end / fan-end bearings with seeded faults, 0-3 hp loads
CWRU_BASE = "https://engineering.case.edu/bearingdatacenter/"
CWRU_PAGES = ["normal-baseline-data", "12k-drive-end-bearing-fault-data",
              "12k-fan-end-bearing-fault-data", "48k-drive-end-bearing-fault-data"]
CWRU_LINK = re.compile(r'href="(https://engineering\.case\.edu/sites/default/files/(\d+)\.mat)"[^>]*>([^<]+)')

# UCI zips: (folder, zip url, note)
UCI_ZIPS = [
    ("uci_sensorless_drive_diagnosis",
     "https://archive.ics.uci.edu/static/public/325/dataset+for+sensorless+drive+diagnosis.zip",
     "UCI 325 - motor phase currents of a synchronous drive, 11 fault classes; CC BY 4.0"),
]
