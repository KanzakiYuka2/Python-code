"""Add verified numbered citations to the CONNEX manuscript DOCX.

The DOCX package is edited at XML level so existing paragraphs, equations,
images, tables, styles, and page layout remain otherwise unchanged.
"""

from pathlib import Path
from xml.sax.saxutils import escape
import zipfile


SOURCE = Path("前刷り_リムCONNEX.docx")
OUTPUT = Path("前刷り_リムCONNEX_引用追加.docx")


def replace_once(xml: str, old: str, new: str) -> str:
    count = xml.count(old)
    if count != 1:
        raise ValueError(
            f"Expected exactly one occurrence, found {count}: {old!r}"
        )
    return xml.replace(old, new, 1)


references = [
    (
        "[1] Y. Su, H. Lv, W. Zhou, and C. Zhang, “Review of the Hydrogen "
        "Permeability of the Liner Material of Type IV On-Board Hydrogen "
        "Storage Tank,” World Electric Vehicle Journal, vol. 12, no. 3, "
        "p. 130, 2021. doi: 10.3390/wevj12030130."
    ),
    (
        "[2] L. Lei, Y. Yan, T. Liu, Y. Hao, J. Chai, Z. Zhuang, W. Wei, "
        "Z. Ni, and J. Zhang, “Permeability modeling and mechanical "
        "performance of multi-ply heterogeneous composites for linerless "
        "hydrogen storage tanks,” Composites Part B: Engineering, vol. 322, "
        "p. 113743, 2026. doi: 10.1016/j.compositesb.2026.113743."
    ),
    (
        "[3] T. Yokozeki, T. Ogasawara, and T. Ishikawa, “Evaluation of gas "
        "leakage through composite laminates with multilayer matrix cracks: "
        "Cracking angle effects,” Composites Science and Technology, vol. 66, "
        "no. 15, pp. 2815–2824, 2006. doi: 10.1016/j.compscitech.2006.02.024."
    ),
    (
        "[4] T. Yokozeki, T. Ogasawara, T. Aoki, and T. Ishikawa, "
        "“Experimental evaluation of gas permeability through damaged "
        "composite laminates for cryogenic tank,” Composites Science and "
        "Technology, vol. 69, no. 9, pp. 1334–1340, 2009. "
        "doi: 10.1016/j.compscitech.2008.05.019."
    ),
    (
        "[5] J. G. Wijmans and R. W. Baker, “The solution-diffusion model: "
        "a review,” Journal of Membrane Science, vol. 107, nos. 1–2, "
        "pp. 1–21, 1995. doi: 10.1016/0376-7388(95)00102-I."
    ),
    (
        "[6] B. R. Murray, S. B. Leen, C. O. A. Semprimoschnig, and "
        "C. M. Ó Brádaigh, “Helium permeability of polymer materials as "
        "liners for composite overwrapped pressure vessels,” Journal of "
        "Applied Polymer Science, vol. 133, no. 29, p. 43675, 2016. "
        "doi: 10.1002/app.43675."
    ),
    (
        "[7] L. Monson, S. I. Moon, and C. W. Extrand, “Permeation resistance "
        "of poly(ether ether ketone) to hydrogen, nitrogen, and oxygen "
        "gases,” Journal of Applied Polymer Science, vol. 127, no. 3, "
        "pp. 1637–1642, 2013. doi: 10.1002/app.37517."
    ),
    (
        "[8] J. Condé-Wolter, M. G. Ruf, A. Liebsch, T. Lebelt, I. Koch, "
        "K. Drechsler, and M. Gude, “Hydrogen permeability of thermoplastic "
        "composites and liner systems for future mobility applications,” "
        "Composites Part A: Applied Science and Manufacturing, vol. 167, "
        "p. 107446, 2023. doi: 10.1016/j.compositesa.2023.107446."
    ),
]


with zipfile.ZipFile(SOURCE, "r") as source_zip:
    document_xml = source_zip.read("word/document.xml").decode("utf-8")

    # Introduction: CFRP tanks, tank types, and linerless development.
    document_xml = replace_once(
        document_xml,
        "水素タンク貯蔵タンクの軽量化に有望な材料である。",
        "水素タンク貯蔵タンクの軽量化に有望な材料である[1]。",
    )
    document_xml = replace_once(
        document_xml,
        "タンクの開発は今進んでいる",
        "タンクの開発は今進んでいる[1,2]",
    )

    # Introduction: damage-induced leakage and solution-diffusion.
    old_transport_text = (
        "気体漏洩については，マトリクスクラックなどの損傷を介した漏洩挙動に"
        "関する研究が進められている．一方，損傷のない材料内部を気体分子が"
        "溶解・拡散することによって生じる透過挙動については，十分に明らかに"
        "なっていない．"
    )
    new_transport_text = (
        "気体漏洩については，マトリクスクラックなどの損傷を介した漏洩挙動に"
        "関する研究が進められている[3,4]．一方，損傷のない材料内部を気体分子が"
        "溶解・拡散することによって生じる透過挙動については，十分に明らかに"
        "なっていない[1,5]．"
    )
    document_xml = replace_once(
        document_xml, old_transport_text, new_transport_text
    )
    document_xml = replace_once(
        document_xml,
        "全体の透過特性を理解する上では，その基礎となるマトリックス樹脂単体の"
        "ガス透過特性を把握することが重要である．",
        "全体の透過特性を理解する上では，その基礎となるマトリックス樹脂単体の"
        "ガス透過特性を把握することが重要である[6,7]．",
    )

    # Half-time/Fickian method and steady-state permeability equations.
    document_xml = replace_once(
        document_xml,
        "ハーフタイム法で算出した．",
        "ハーフタイム法で算出した[8]．",
    )
    document_xml = replace_once(
        document_xml,
        "に相当する値に達するまでの時間であり，自作の解析プログラムを用いて"
        "自動的に算出した",
        "に相当する値に達するまでの時間であり，自作の解析プログラムを用いて"
        "自動的に算出した[8]",
    )
    document_xml = replace_once(
        document_xml,
        "は以下の式を使って算出した．",
        "は以下の式を使って算出した[6,8]．",
    )

    # Add the numbered bibliography immediately before the final section
    # properties, leaving all earlier document content untouched.
    reference_xml = "".join(
        "<w:p><w:pPr><w:spacing w:after=\"0\"/></w:pPr>"
        "<w:r><w:rPr><w:rFonts w:ascii=\"Times New Roman\" "
        "w:hAnsi=\"Times New Roman\" w:eastAsia=\"MS Mincho\"/>"
        "<w:sz w:val=\"18\"/><w:szCs w:val=\"18\"/></w:rPr>"
        f"<w:t>{escape(reference)}</w:t></w:r></w:p>"
        for reference in references
    )

    section_marker = "<w:sectPr"
    marker_position = document_xml.rfind(section_marker)
    if marker_position == -1:
        raise ValueError("Could not locate the document section properties.")
    document_xml = (
        document_xml[:marker_position]
        + reference_xml
        + document_xml[marker_position:]
    )

    with zipfile.ZipFile(OUTPUT, "w") as output_zip:
        for item in source_zip.infolist():
            data = (
                document_xml.encode("utf-8")
                if item.filename == "word/document.xml"
                else source_zip.read(item.filename)
            )
            output_zip.writestr(item, data)

print(OUTPUT.resolve())
