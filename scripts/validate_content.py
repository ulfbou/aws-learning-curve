"""
Increment 0 validation - Python
ADR-001..010
"""
import re, sys, json, hashlib
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+){1,10}$")
HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")
FP_PATTERN = re.compile(r"^[a-f0-9]{16,64}$")

def load_yaml_glob(pattern):
    objs=[]
    for p in ROOT.glob(pattern):
        if not p.is_file() or p.name==".gitkeep": continue
        doc=yaml.safe_load(p.read_text(encoding="utf-8"))
        if doc is None: continue
        if isinstance(doc,list): objs.extend([d for d in doc if isinstance(d,dict)])
        else: objs.append(doc)
    return objs

def load_all():
    all_objs={}
    for pat in ["content/sources/**/*.yaml","content/concepts/**/*.yaml","content/competencies/**/*.yaml",
                "content/learning-units/**/*.yaml","content/questions/**/*.yaml","content/scenarios/**/*.yaml",
                "content/procedures/**/*.yaml","content/misconceptions/**/*.yaml","content/generation-runs/**/*.yaml"]:
        for obj in load_yaml_glob(pat):
            if "id" not in obj:
                print(f"Missing id in {pat}", file=sys.stderr); sys.exit(1)
            oid=obj["id"]
            if oid in all_objs and oid not in obj.get("aliases",[]):
                print(f"Duplicate ID {oid}", file=sys.stderr); sys.exit(1)
            all_objs[oid]=obj
    return all_objs

def validate_common(all_objs):
    ok=True
    for oid,obj in all_objs.items():
        kind=obj.get("kind")
        if kind!="generation_run":
            for f in ["revision","created_at","updated_at","content_hash"]:
                if f not in obj:
                    print(f"Missing {f} in {oid}", file=sys.stderr); ok=False
        if not ID_PATTERN.match(oid) or len(oid)>128:
            print(f"ID pattern fail {oid}", file=sys.stderr); ok=False
        if "content_hash" in obj and not HASH_PATTERN.match(obj["content_hash"]):
            print(f"Bad hash {oid}", file=sys.stderr); ok=False
        if kind=="source" and "fragments" in obj:
            for frag in obj["fragments"]:
                if "language" not in frag or "content_fingerprint" not in frag:
                    print(f"Fragment missing lang/fp {oid}/{frag.get('id')}", file=sys.stderr); ok=False
    return ok

def custom(all_objs):
    ok=True
    alias_map={}
    for oid,obj in all_objs.items():
        for a in obj.get("aliases",[]):
            if a in alias_map and alias_map[a]!=oid:
                print(f"Alias conflict {a}", file=sys.stderr); ok=False
            alias_map[a]=oid
    def resolve(r):
        return r if r in all_objs else alias_map.get(r)
    def get_refs(obj):
        refs=[]
        def push(v):
            if isinstance(v,str) and "." in v and ID_PATTERN.match(v):
                refs.append(v)
        for k in ["prerequisite_ids","concept_ids","competency_ids","learning_objectives","prerequisite_competencies",
                  "recommended_question_ids","misconception_ids","question_ids","scenario_ids","learning_unit_ids"]:
            v=obj.get(k)
            if isinstance(v,list):
                for x in v: push(x)
        rc=obj.get("recommended_content")
        if isinstance(rc,dict):
            for vv in rc.values():
                if isinstance(vv,list):
                    for x in vv: push(x)
        for rel in obj.get("relationships",[]):
            push(rel.get("target_id"))
        for m in obj.get("members",[]):
            push(m.get("concept_id"))
        for sec in obj.get("sections",[]):
            for kk in ["concept_ids","question_ids","scenario_ids"]:
                for x in sec.get(kk,[]): push(x)
        return refs

    for oid,obj in all_objs.items():
        if obj.get("status")!="published": continue
        for ref in get_refs(obj):
            res=resolve(ref)
            if not res:
                print(f"Unresolved {oid} -> {ref}", file=sys.stderr); ok=False
            else:
                tgt=all_objs.get(res)
                if tgt and tgt.get("status")!="published" and tgt.get("kind") not in ("source","generation_run"):
                    print(f"Published {oid} refs non-published {res} ({tgt.get('status')})", file=sys.stderr); ok=False
        if obj.get("kind") in ("concept","competency","learning_unit","question","scenario","procedure","misconception"):
            prov=obj.get("provenance")
            if prov and prov.get("transformation",{}).get("method","").startswith("llm_"):
                if not prov.get("sources"):
                    print(f"Missing grounding {oid}", file=sys.stderr); ok=False
            grounding=obj.get("grounding",{})
            if grounding.get("unsupported_claims") and obj.get("status")=="published":
                print(f"Unsupported claims in published {oid}", file=sys.stderr); ok=False
    for oid,obj in all_objs.items():
        if obj.get("kind")=="concept" and obj.get("concept_type")=="contrast":
            members=obj.get("members")
            if not members or len(members)!=2:
                print(f"Contrast {oid} needs 2 members", file=sys.stderr); ok=False
            else:
                k0=sorted((members[0].get("dimensions") or {}).keys())
                k1=sorted((members[1].get("dimensions") or {}).keys())
                if k0!=k1:
                    print(f"Contrast {oid} dimension mismatch {k0} vs {k1}", file=sys.stderr); ok=False
    return ok

def main():
    print("🔍 Increment 0 validation - Python ADR-001..010")
    all_objs=load_all()
    print(f"Loaded {len(all_objs)} objects")
    ok1=validate_common(all_objs)
    ok2=custom(all_objs)
    if not (ok1 and ok2):
        print("❌ Validation failed", file=sys.stderr); sys.exit(1)
    print("✅ All validations passed")

if __name__=="__main__":
    main()
