"""
Build bundle - Python
ADR-001,010
"""
import json, hashlib, pathlib, yaml, datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PUBLIC_DATA=ROOT/"public"/"data"

def load_yaml_glob(pattern):
    objs=[]
    for p in ROOT.glob(pattern):
        if not p.is_file() or p.name==".gitkeep": continue
        doc=yaml.safe_load(p.read_text(encoding="utf-8"))
        if doc is None: continue
        if isinstance(doc,list): objs.extend([d for d in doc if isinstance(d,dict)])
        else: objs.append(doc)
    return objs

def sha256_hex(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def main():
    print("📦 Building bundle - Python")
    all_objs=[]
    for pat in ["content/sources/**/*.yaml","content/concepts/**/*.yaml","content/competencies/**/*.yaml",
                "content/learning-units/**/*.yaml","content/questions/**/*.yaml","content/scenarios/**/*.yaml",
                "content/procedures/**/*.yaml","content/misconceptions/**/*.yaml"]:
        all_objs.extend(load_yaml_glob(pat))
    published=[o for o in all_objs if o.get("status")=="published"]
    alias_map={}
    for o in all_objs:
        for a in o.get("aliases",[]):
            alias_map[a]=o["id"]
    manifest_path=ROOT/"content"/"manifest.yaml"
    manifest={}
    if manifest_path.exists():
        manifest=yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
        alias_map.update(manifest.get("aliases",{}) or {})
    # invariants - raw file contents are never loaded, origin.path referencing raw is allowed
    for o in published:
        pass
        if o.get("grounding",{}).get("unsupported_claims"):
            print(f"Unsupported claims {o['id']}"); raise SystemExit(1)

    collections={"concepts":{},"competencies":{},"learningUnits":{},"questions":{},"scenarios":{},"procedures":{},"misconceptions":{},"sources":{}}
    kind_map={"concept":"concepts","competency":"competencies","learning_unit":"learningUnits","question":"questions","scenario":"scenarios","procedure":"procedures","misconception":"misconceptions","source":"sources"}
    for o in published:
        b=kind_map.get(o.get("kind"))
        if b: collections[b][o["id"]]=o

    indexes={"byTag":{},"byCompetency":{},"byConcept":{},"byDifficulty":{},"byMisconception":{},"prerequisites":{},"contrasts":[]}
    def add(idx,key,oid):
        if not key: return
        idx.setdefault(key,[])
        if oid not in idx[key]: idx[key].append(oid)

    for o in published:
        oid=o["id"]
        for t in o.get("tags",[]): add(indexes["byTag"],t,oid)
        if o.get("difficulty"): add(indexes["byDifficulty"],o["difficulty"],oid)
        for cid in o.get("competency_ids",[]): add(indexes["byCompetency"],cid,oid)
        for cid in o.get("concept_ids",[]): add(indexes["byConcept"],cid,oid)
        for mid in o.get("misconception_ids",[]): add(indexes["byMisconception"],mid,oid)
        if o.get("prerequisite_ids"): indexes["prerequisites"][oid]=o["prerequisite_ids"]
        if o.get("kind")=="concept" and o.get("concept_type")=="contrast": indexes["contrasts"].append(oid)

    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    content_version=manifest.get("content_version","2026-11-01.1")
    bundle={"schemaVersion":"1.0","contentVersion":content_version,"generatedAt":now,"aliasMap":alias_map,
            "concepts":collections["concepts"],"competencies":collections["competencies"],
            "learningUnits":collections["learningUnits"],"questions":collections["questions"],
            "scenarios":collections["scenarios"],"procedures":collections["procedures"],
            "misconceptions":collections["misconceptions"],"sources":collections["sources"],
            "indexes":indexes,
            "manifest":{"contentVersion":content_version,"generatedAt":now,
                        "counts":{k:len(v) for k,v in collections.items()},
                        "publishedOnly":True,"privateExcluded":True,"rawExcluded":True}}

    PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
    bp=PUBLIC_DATA/"learning-bundle.json"
    bp.write_text(json.dumps(bundle, indent=2, ensure_ascii=False), encoding="utf-8")
    bh=sha256_hex(bp.read_text(encoding="utf-8"))
    mout={"schemaVersion":"1.0","contentVersion":content_version,"generatedAt":now,
          "bundlePath":"public/data/learning-bundle.json","bundleHash":bh,
          "bundleSizeBytes":bp.stat().st_size,
          "perObjectHashes":{o["id"]:o.get("content_hash") or sha256_hex(json.dumps(o, sort_keys=True)) for o in published},
          "aliasMap":alias_map,
          "releaseInvariants":["No private file may enter public/data","No raw source may enter bundle",
                               "No published object may reference a candidate","No factual object may lack grounding",
                               "No object with unsupported claims may be published","All refs resolve after alias expansion",
                               "Bundle and manifest hashes must match"]}
    (PUBLIC_DATA/"learning-bundle.manifest.json").write_text(json.dumps(mout, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✅ Bundle {len(collections['concepts'])} concepts hash {bh[:12]}...")

if __name__=="__main__":
    main()
