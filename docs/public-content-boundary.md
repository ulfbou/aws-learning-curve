# Public content boundary

Registered source material and public learning content have different
responsibilities.

## First-phase policy

Registered `source` objects remain canonical backend content. They are
available to deterministic tooling, bounded learning contexts, grounding,
provenance review, and repository validation.

Registered source objects are not public content in this phase.

The public release therefore:

- excludes every serialized `source` object;
- retains an empty `sources` compatibility collection;
- excludes source fragments, exact text, normalized text, fingerprints,
  locators, and local source paths;
- excludes aliases whose target is not a public learning object;
- builds public indexes and per-object hashes only from serialized public
  learning objects;
- allows learning objects to retain source and fragment IDs for grounding;
- excludes private learner state and transient collaboration paths.

No metadata-only public source projection is introduced.

## Public artifact validation

Release verification recursively inspects generated JSON and rejects:

- `exact_text`;
- `normalized_text`;
- source content fingerprints;
- fragment locator data;
- `origin.path`;
- private learner-state fields;
- `.dx/`, `.private/`, and `.authoring/` path markers.

Regression fixtures use unmistakable sentinel values to prove that registered
source content is absent from the produced artifact. The test is not satisfied
merely by checking for common source field names.

## Compatibility decision

The public bundle retains:

```json
{
  "sources": {}
}
```

This preserves the current frontend bundle shape without presenting registered
sources as public cards.

The frontend already treats empty collections as having no items and renders
group controls only when matching items exist. No frontend rendering change is
required for this boundary.

## Deliberately unchanged

This policy does not:

- remove grounding source IDs from learning objects;
- remove provenance source and fragment IDs;
- redesign provenance;
- change the source schema;
- create a public source schema;
- automate source registration;
- introduce automatic redaction;
- add publication commands;
- change the bounded learning transaction;
- publish IAM content.

A later metadata-only source projection requires a demonstrated learner need
and a separately reviewed public schema.
