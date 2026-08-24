"""
Formulaire d'adhésion en ligne — DAHIRA THIERNO HADY WELE RTA
----------------------------------------------------------------
Application web (Streamlit) : les membres remplissent le formulaire
depuis leur téléphone via un lien, les données sont centralisées dans
une base SQLite partagée, et chaque membre peut télécharger sa carte
de membre en PDF immédiatement après validation.

Déploiement : voir les instructions fournies séparément
(Streamlit Community Cloud, gratuit).
"""

import streamlit as st
import sqlite3
import os
import io
import math
import re
from datetime import date

from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

# ======================================================================
# Configuration générale
# ======================================================================
NOM_ORGANISATION = "DAHIRA THIERNO HADY WELE RTA"
SOUS_TITRE_CARTE = "Carte de Membre"

OR_GOLD = (199, 166, 97)
OR_GOLD_CLAIR = (230, 205, 150)
NAVY_DARK = (7, 16, 34)
NAVY_LIGHT = (19, 42, 78)
CREME = (248, 246, 240)
GRIS_DOUX = (190, 199, 214)

DOSSIER_SCRIPT = os.path.dirname(os.path.abspath(__file__))
FICHIER_DB = os.path.join(DOSSIER_SCRIPT, "adhesions.db")

TYPES_ADHESION = ["Membre actif", "Membre honoraire", "Membre bienfaiteur", "Membre d'honneur"]


# ======================================================================
# Base de données (SQLite — un seul fichier partagé par tous les
# utilisateurs de l'application déployée)
# ======================================================================
def initialiser_db():
    conn = sqlite3.connect(FICHIER_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS adhesions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_membre TEXT UNIQUE,
            date_adhesion TEXT,
            nom TEXT,
            prenom TEXT,
            naissance TEXT,
            sexe TEXT,
            adresse TEXT,
            telephone TEXT,
            email TEXT,
            profession TEXT,
            type_adhesion TEXT
        )
    """)
    conn.commit()
    conn.close()


def prochain_numero_membre():
    conn = sqlite3.connect(FICHIER_DB)
    cur = conn.execute("SELECT COUNT(*) FROM adhesions")
    total = cur.fetchone()[0]
    conn.close()
    return f"M{total + 1:04d}"


def enregistrer_adhesion(donnees):
    conn = sqlite3.connect(FICHIER_DB)
    conn.execute("""
        INSERT INTO adhesions
        (numero_membre, date_adhesion, nom, prenom, naissance, sexe,
         adresse, telephone, email, profession, type_adhesion)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        donnees["numero_membre"], donnees["date_adhesion"], donnees["nom"],
        donnees["prenom"], donnees["naissance"], donnees["sexe"],
        donnees["adresse"], donnees["telephone"], donnees["email"],
        donnees["profession"], donnees["type_adhesion"],
    ))
    conn.commit()
    conn.close()


def compter_membres():
    conn = sqlite3.connect(FICHIER_DB)
    cur = conn.execute("SELECT COUNT(*) FROM adhesions")
    total = cur.fetchone()[0]
    conn.close()
    return total


def tous_les_membres():
    conn = sqlite3.connect(FICHIER_DB)
    cur = conn.execute("""
        SELECT numero_membre, date_adhesion, nom, prenom, naissance, sexe,
               adresse, telephone, email, profession, type_adhesion
        FROM adhesions ORDER BY id
    """)
    lignes = cur.fetchall()
    conn.close()
    return lignes


# ======================================================================
# Génération de la carte de membre (même design que la version bureau :
# fond dégradé, cadre doré, emblème vectoriel en filigrane)
# ======================================================================
def _polices_disponibles():
    candidats_bold = [
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "C:/Windows/Fonts/georgiab.ttf",
        "C:/Windows/Fonts/timesbd.ttf",
    ]
    candidats_regular = [
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "C:/Windows/Fonts/georgia.ttf",
        "C:/Windows/Fonts/times.ttf",
    ]
    candidats_italique = [
        "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
        "C:/Windows/Fonts/georgiai.ttf",
        "C:/Windows/Fonts/timesi.ttf",
    ]

    def _premier_existant(chemins):
        for c in chemins:
            if os.path.exists(c):
                return c
        return None

    return (
        _premier_existant(candidats_bold),
        _premier_existant(candidats_regular),
        _premier_existant(candidats_italique),
    )


def _degrade(largeur, hauteur, c1, c2, angle_deg=30):
    base = Image.new("RGB", (largeur, hauteur), c1)
    haut = Image.new("RGB", (largeur, hauteur), c2)
    masque = Image.new("L", (largeur, hauteur))
    md = masque.load()
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad), math.sin(rad)
    coins = [(0, 0), (largeur, 0), (0, hauteur), (largeur, hauteur)]
    projs = [x * dx + y * dy for x, y in coins]
    pmin, pmax = min(projs), max(projs)
    etendue = (pmax - pmin) or 1
    for y in range(hauteur):
        for x in range(0, largeur, 2):
            p = (x * dx + y * dy - pmin) / etendue
            val = int(255 * max(0, min(1, p)))
            md[x, y] = val
            if x + 1 < largeur:
                md[x + 1, y] = val
    base.paste(haut, (0, 0), masque)
    return base


def _texte_multiligne(texte, police, largeur_max, draw):
    mots = texte.split()
    lignes, courant = [], ""
    for mot in mots:
        essai = (courant + " " + mot).strip()
        if draw.textlength(essai, font=police) <= largeur_max:
            courant = essai
        else:
            if courant:
                lignes.append(courant)
            courant = mot
    if courant:
        lignes.append(courant)
    return lignes


def _dessiner_embleme(taille, couleur, opacite=0.16):
    img = Image.new("RGBA", (taille, taille), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx, cy = taille // 2, taille // 2
    alpha = max(0, min(255, int(255 * opacite)))
    coul = tuple(couleur) + (alpha,)
    coul_fin = tuple(couleur) + (max(0, alpha - 40),)

    r_ext = int(taille * 0.46)
    r_int = int(taille * 0.42)
    epaisseur = max(2, taille // 220)

    d.ellipse([cx - r_ext, cy - r_ext, cx + r_ext, cy + r_ext], outline=coul, width=epaisseur)
    d.ellipse([cx - r_int, cy - r_int, cx + r_int, cy + r_int], outline=coul_fin, width=max(1, epaisseur - 1))

    nb_reperes = 32
    r1 = int(taille * 0.42)
    r2 = int(taille * 0.395)
    for i in range(nb_reperes):
        angle = 2 * math.pi * i / nb_reperes
        x1, y1 = cx + r1 * math.cos(angle), cy + r1 * math.sin(angle)
        x2, y2 = cx + r2 * math.cos(angle), cy + r2 * math.sin(angle)
        d.line([(x1, y1), (x2, y2)], fill=coul_fin, width=max(1, epaisseur - 1))

    r_pointe = int(taille * 0.16)
    r_creux = int(taille * 0.065)
    points = []
    nb_branches = 8
    for i in range(nb_branches * 2):
        angle = math.pi * i / nb_branches - math.pi / 2
        rayon = r_pointe if i % 2 == 0 else r_creux
        points.append((cx + rayon * math.cos(angle), cy + rayon * math.sin(angle)))
    d.polygon(points, outline=coul, width=epaisseur)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=coul)
    return img


def generer_carte_membre_pdf(donnees):
    """Retourne les octets du PDF de la carte de membre (pour téléchargement direct)."""
    DPI = 300
    LARGEUR = round(85.6 / 25.4 * DPI)
    HAUTEUR = round(54.0 / 25.4 * DPI)

    carte = _degrade(LARGEUR, HAUTEUR, NAVY_DARK, NAVY_LIGHT, 30).convert("RGBA")

    try:
        taille_wm = int(HAUTEUR * 1.5)
        filigrane = _dessiner_embleme(taille_wm, CREME, opacite=0.16)
        carte.alpha_composite(filigrane, (LARGEUR - int(taille_wm * 0.60), int(-taille_wm * 0.20)))
    except Exception:
        pass

    draw = ImageDraw.Draw(carte)
    marge = 16
    draw.rectangle([marge, marge, LARGEUR - marge, HAUTEUR - marge], outline=OR_GOLD, width=3)
    marge2 = marge + 7
    draw.rectangle([marge2, marge2, LARGEUR - marge2, HAUTEUR - marge2], outline=OR_GOLD, width=1)

    def coin(x, y, dx, dy, longueur=26):
        draw.line([(x, y), (x + dx * longueur, y)], fill=OR_GOLD_CLAIR, width=3)
        draw.line([(x, y), (x, y + dy * longueur)], fill=OR_GOLD_CLAIR, width=3)

    coin(marge - 2, marge - 2, 1, 1)
    coin(LARGEUR - marge + 2, marge - 2, -1, 1)
    coin(marge - 2, HAUTEUR - marge + 2, 1, -1)
    coin(LARGEUR - marge + 2, HAUTEUR - marge + 2, -1, -1)

    chemin_bold, chemin_regular, chemin_italique = _polices_disponibles()
    try:
        f_org = ImageFont.truetype(chemin_bold, 34) if chemin_bold else ImageFont.load_default()
        f_sous_titre = ImageFont.truetype(chemin_italique, 19) if chemin_italique else ImageFont.load_default()
        f_nom = ImageFont.truetype(chemin_bold, 40) if chemin_bold else ImageFont.load_default()
        f_label = ImageFont.truetype(chemin_regular, 20) if chemin_regular else ImageFont.load_default()
        f_valeur = ImageFont.truetype(chemin_bold, 20) if chemin_bold else ImageFont.load_default()
    except Exception:
        f_org = f_sous_titre = f_nom = f_label = f_valeur = ImageFont.load_default()

    pad = marge2 + 26
    zone_largeur = int(LARGEUR * 0.60)

    y = pad
    for ligne in _texte_multiligne(NOM_ORGANISATION, f_org, zone_largeur, draw):
        draw.text((pad, y), ligne, font=f_org, fill=OR_GOLD_CLAIR)
        y += 40

    draw.text((pad, y + 2), SOUS_TITRE_CARTE, font=f_sous_titre, fill=GRIS_DOUX)
    y += 34
    draw.line([(pad, y + 10), (pad + zone_largeur, y + 10)], fill=OR_GOLD, width=1)
    y += 30

    nom_complet = f"{donnees['prenom']} {donnees['nom']}".upper()
    for ligne in _texte_multiligne(nom_complet, f_nom, zone_largeur, draw):
        draw.text((pad, y), ligne, font=f_nom, fill=CREME)
        y += 48

    y += 4
    infos = [
        ("N° de membre", donnees["numero_membre"]),
        ("Catégorie", donnees["type_adhesion"] or "Membre"),
        ("Adhésion", donnees["date_adhesion"]),
    ]
    for label, val in infos:
        draw.text((pad, y), f"{label} :", font=f_label, fill=GRIS_DOUX)
        lx = pad + draw.textlength(f"{label} :  ", font=f_label)
        draw.text((lx, y), val, font=f_valeur, fill=OR_GOLD_CLAIR)
        y += 30

    tampon_image = io.BytesIO()
    carte.convert("RGB").save(tampon_image, format="PNG")
    tampon_image.seek(0)

    tampon_pdf = io.BytesIO()
    largeur_pt, hauteur_pt = 85.6 * mm, 54 * mm
    c = canvas.Canvas(tampon_pdf, pagesize=(largeur_pt, hauteur_pt))
    c.drawImage(ImageReader(tampon_image), 0, 0, width=largeur_pt, height=hauteur_pt)
    c.showPage()
    c.save()
    tampon_pdf.seek(0)
    return tampon_pdf.getvalue()


# ======================================================================
# Interface Streamlit
# ======================================================================
st.set_page_config(page_title=f"Adhésion — {NOM_ORGANISATION}", page_icon="🕌", layout="centered")
initialiser_db()

st.title(NOM_ORGANISATION)
st.subheader("Formulaire d'adhésion en ligne")
st.caption(f"{compter_membres()} membre(s) déjà inscrit(s)")

with st.form("formulaire_adhesion", clear_on_submit=False):
    col1, col2 = st.columns(2)
    with col1:
        nom = st.text_input("Nom *")
        naissance = st.text_input("Date de naissance (JJ/MM/AAAA)")
        adresse = st.text_input("Adresse")
        email = st.text_input("Email")
    with col2:
        prenom = st.text_input("Prénom *")
        sexe = st.selectbox("Sexe", ["", "Femme", "Homme"])
        telephone = st.text_input("Téléphone *")
        profession = st.text_input("Profession")

    type_adhesion = st.selectbox("Type d'adhésion", TYPES_ADHESION)

    st.caption("* champs obligatoires")
    valider = st.form_submit_button("Valider mon adhésion", use_container_width=True)

if valider:
    erreurs = []
    if not nom.strip():
        erreurs.append("Le nom est obligatoire.")
    if not prenom.strip():
        erreurs.append("Le prénom est obligatoire.")
    if not telephone.strip():
        erreurs.append("Le téléphone est obligatoire.")
    if email.strip() and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
        erreurs.append("L'adresse email n'est pas valide.")

    if erreurs:
        for e in erreurs:
            st.error(e)
    else:
        numero_membre = prochain_numero_membre()
        donnees = {
            "numero_membre": numero_membre,
            "date_adhesion": date.today().strftime("%d/%m/%Y"),
            "nom": nom.strip(),
            "prenom": prenom.strip(),
            "naissance": naissance.strip(),
            "sexe": sexe,
            "adresse": adresse.strip(),
            "telephone": telephone.strip(),
            "email": email.strip(),
            "profession": profession.strip(),
            "type_adhesion": type_adhesion,
        }

        try:
            enregistrer_adhesion(donnees)
        except sqlite3.IntegrityError:
            # en cas de rare collision de numéro (soumissions simultanées), on réessaie une fois
            donnees["numero_membre"] = prochain_numero_membre()
            enregistrer_adhesion(donnees)

        st.success(f"Adhésion enregistrée avec succès ! Numéro de membre : {donnees['numero_membre']}")

        pdf_bytes = generer_carte_membre_pdf(donnees)
        st.download_button(
            "📇 Télécharger ma carte de membre (PDF)",
            data=pdf_bytes,
            file_name=f"carte_{donnees['numero_membre']}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )

# ----------------------------------------------------------------------
# Espace administrateur (protégé par mot de passe simple)
# ----------------------------------------------------------------------
with st.expander("🔒 Espace administrateur"):
    mot_de_passe = st.text_input("Mot de passe", type="password", key="admin_pwd")
    # Changez ce mot de passe avant de déployer publiquement !
    MOT_DE_PASSE_ADMIN = "dahira2026"

    if mot_de_passe:
        if mot_de_passe == MOT_DE_PASSE_ADMIN:
            lignes = tous_les_membres()
            st.write(f"**{len(lignes)} membre(s) au total**")
            if lignes:
                import pandas as pd
                colonnes = ["Numéro", "Date", "Nom", "Prénom", "Naissance", "Sexe",
                            "Adresse", "Téléphone", "Email", "Profession", "Type"]
                df = pd.DataFrame(lignes, columns=colonnes)
                st.dataframe(df, use_container_width=True)

                tampon_excel = io.BytesIO()
                df.to_excel(tampon_excel, index=False, engine="openpyxl")
                tampon_excel.seek(0)
                st.download_button(
                    "⬇️ Télécharger toutes les adhésions (Excel)",
                    data=tampon_excel.getvalue(),
                    file_name="adhesions.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
        else:
            st.error("Mot de passe incorrect.")
