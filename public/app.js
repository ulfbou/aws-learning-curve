const DATA_URL = new URL("./data/", window.location.href);

const GROUPS = [
  ["concepts", "Begrepp"],
  ["competencies", "Kompetenser"],
  ["learningUnits", "Lärmoment"],
  ["questions", "Frågor"],
  ["scenarios", "Scenarier"],
  ["procedures", "Procedurer"],
  ["misconceptions", "Missuppfattningar"],
  ["sources", "Källor"],
];

const state = {
  bundle: null,
  manifest: null,
  query: "",
  group: "all",
  tag: "all",
  selected: null,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function local(value) {
  if (value == null) {
    return "";
  }

  if (typeof value === "string") {
    return value;
  }

  if (typeof value !== "object") {
    return String(value);
  }

  const localized = value["sv-SE"] ?? value.en ?? value;

  if (typeof localized === "string") {
    return localized;
  }

  if (localized && typeof localized.preferred === "string") {
    return localized.preferred;
  }

  if (localized && typeof localized.text === "string") {
    return localized.text;
  }

  return "";
}

function title(item) {
  return (
    local(item.labels) ||
    local(item.title) ||
    local(item.statement) ||
    item.id ||
    "Namnlöst objekt"
  );
}

function summary(item) {
  return (
    local(item.definition) ||
    local(item.description) ||
    local(item.summary) ||
    local(item.correction) ||
    local(item.normalized_text) ||
    "Ingen beskrivning ännu."
  );
}

function pointText(point) {
  if (typeof point === "string") {
    return point;
  }

  return local(point?.text ?? point);
}

async function getJson(name, signal, version = "") {
  const url = new URL(name, DATA_URL);

  if (version) {
    url.searchParams.set("v", version);
  }

  const response = await fetch(url, {
    method: "GET",
    headers: {
      Accept: "application/json",
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(
      `${response.status} ${response.statusText}: ${url.pathname}`
    );
  }

  return response.json();
}

function flattenBundle(bundle) {
  return GROUPS.flatMap(([key, label]) => {
    const collection = bundle[key] ?? {};

    return Object.values(collection).map((item) => ({
      ...item,
      _group: key,
      _label: label,
    }));
  });
}

function allItems() {
  return state.bundle ? flattenBundle(state.bundle) : [];
}

function filteredItems() {
  const query = state.query.trim().toLocaleLowerCase("sv-SE");

  return allItems().filter((item) => {
    const groupMatches =
      state.group === "all" || item._group === state.group;

    const tagMatches =
      state.tag === "all" || (item.tags ?? []).includes(state.tag);

    const searchable = [
      item.id,
      title(item),
      summary(item),
      ...(item.tags ?? []),
    ]
      .join(" ")
      .toLocaleLowerCase("sv-SE");

    const queryMatches = !query || searchable.includes(query);

    return groupMatches && tagMatches && queryMatches;
  });
}

function renderPill(label, active, attributes = "") {
  const colors = active
    ? "border-navy bg-navy text-white"
    : "border-slate-200 bg-white text-slate-600 hover:border-slate-400";

  return `
    <button
      type="button"
      class="rounded-full border px-3 py-1 text-sm font-medium
             transition ${colors}"
      ${attributes}
    >
      ${escapeHtml(label)}
    </button>
  `;
}

function renderCard(item) {
  const tags = (item.tags ?? [])
    .slice(0, 4)
    .map(
      (tag) => `
        <span
          class="rounded bg-amber-50 px-2 py-1 text-xs text-amber-800"
        >
          #${escapeHtml(tag)}
        </span>
      `
    )
    .join("");

  return `
    <article
      class="flex h-full flex-col rounded-2xl border border-slate-200
             bg-white p-5 shadow-sm transition hover:-translate-y-1
             hover:shadow-panel"
    >
      <div class="mb-4 flex justify-between gap-3">
        <span
          class="rounded-full border border-slate-200 bg-white px-3 py-1
                 text-sm font-medium text-slate-600"
        >
          ${escapeHtml(item._label)}
        </span>

        <span class="text-xs uppercase text-slate-400">
          ${escapeHtml(item.status ?? "publicerad")}
        </span>
      </div>

      <h2 class="text-lg font-bold text-navy">
        ${escapeHtml(title(item))}
      </h2>

      <p class="mt-2 flex-1 text-sm leading-6 text-slate-600">
        ${escapeHtml(summary(item))}
      </p>

      <div class="mt-4 flex flex-wrap gap-2">
        ${tags}
      </div>

      <button
        type="button"
        class="mt-5 text-left text-sm font-semibold text-navy underline
               decoration-aws decoration-2 underline-offset-4"
        data-open-id="${escapeHtml(item.id)}"
      >
        Öppna detaljer
      </button>
    </article>
  `;
}

function renderMembers(item) {
  if (!Array.isArray(item.members) || item.members.length === 0) {
    return "";
  }

  const cards = item.members
    .map((member) => {
      const dimensions = Object.entries(member.dimensions ?? {})
        .map(
          ([key, value]) => `
            <p class="mt-2 text-sm">
              <strong>${escapeHtml(key)}:</strong>
              ${escapeHtml(local(value))}
            </p>
          `
        )
        .join("");

      return `
        <div class="rounded-xl bg-slate-50 p-4">
          <strong>${escapeHtml(member.concept_id)}</strong>
          ${dimensions}
        </div>
      `;
    })
    .join("");

  return `
    <div class="mt-6 grid gap-3 sm:grid-cols-2">
      ${cards}
    </div>
  `;
}

function renderKeyPoints(item) {
  if (!Array.isArray(item.key_points) || item.key_points.length === 0) {
    return "";
  }

  const points = item.key_points
    .map(
      (point) => `
        <li>${escapeHtml(pointText(point))}</li>
      `
    )
    .join("");

  return `
    <section class="mt-6">
      <h3 class="font-bold">Viktiga punkter</h3>
      <ul class="mt-2 list-disc space-y-2 pl-5">
        ${points}
      </ul>
    </section>
  `;
}

function renderDetail(item) {
  if (!item) {
    return "";
  }

  const sourceIds =
    item.grounding?.source_ids ??
    item.provenance?.sources?.map((source) => source.source_id) ??
    [];

  return `
    <div
      id="detail-backdrop"
      class="fixed inset-0 z-50 flex items-end justify-center
             bg-slate-950/55 sm:items-center sm:p-6"
    >
      <section
        class="max-h-[92vh] w-full max-w-3xl overflow-y-auto
               rounded-t-3xl bg-white p-6 shadow-2xl
               sm:rounded-3xl sm:p-8"
        role="dialog"
        aria-modal="true"
        aria-labelledby="detail-title"
      >
        <div class="flex items-start justify-between gap-4">
          <div>
            <span
              class="rounded-full border border-slate-200 bg-white px-3 py-1
                     text-sm font-medium text-slate-600"
            >
              ${escapeHtml(item._label)}
            </span>

            <h2
              id="detail-title"
              class="mt-3 text-2xl font-black text-navy"
            >
              ${escapeHtml(title(item))}
            </h2>
          </div>

          <button
            id="close-detail"
            type="button"
            class="rounded-full border px-3 py-1 text-xl"
            aria-label="Stäng"
          >
            ×
          </button>
        </div>

        <p class="mt-5 leading-7 text-slate-700">
          ${escapeHtml(summary(item))}
        </p>

        ${renderKeyPoints(item)}
        ${renderMembers(item)}

        <div class="mt-6 rounded-xl bg-slate-50 p-4 text-sm">
          <p>
            <strong>ID:</strong>
            ${escapeHtml(item.id)}
          </p>

          <p class="mt-1">
            <strong>Källor:</strong>
            ${escapeHtml(sourceIds.join(", ") || "Ej angivet")}
          </p>

          <p class="mt-1">
            <strong>Revision:</strong>
            ${escapeHtml(item.revision ?? "–")}
          </p>
        </div>
      </section>
    </div>
  `;
}

function render() {
  const app = document.querySelector("#app");

  if (!state.bundle) {
    return;
  }

  const items = allItems();
  const filtered = filteredItems();

  const tags = [...new Set(items.flatMap((item) => item.tags ?? []))]
    .sort((left, right) => left.localeCompare(right, "sv-SE"));

  const groupPills = [
    renderPill(
      "Alla",
      state.group === "all",
      'data-group="all"'
    ),
    ...GROUPS.filter(([key]) =>
      items.some((item) => item._group === key)
    ).map(([key, label]) =>
      renderPill(
        label,
        state.group === key,
        `data-group="${escapeHtml(key)}"`
      )
    ),
  ].join("");

  const tagOptions = [
    '<option value="all">Alla taggar</option>',
    ...tags.map(
      (tag) => `
        <option
          value="${escapeHtml(tag)}"
          ${state.tag === tag ? "selected" : ""}
        >
          ${escapeHtml(tag)}
        </option>
      `
    ),
  ].join("");

  const cards = filtered.length
    ? filtered.map(renderCard).join("")
    : `
      <div
        class="rounded-2xl border border-dashed p-12 text-center
               md:col-span-2 xl:col-span-3"
      >
        Inga objekt matchar filtreringen.
      </div>
    `;

  app.innerHTML = `
    <header class="bg-navy text-white">
      <div class="mx-auto max-w-7xl px-6 py-12">
        <p class="font-semibold uppercase tracking-[.25em] text-aws">
          AWS Learning Curve
        </p>

        <h1 class="mt-3 max-w-3xl text-4xl font-black sm:text-6xl">
          Utforska kunskap, samband och källor
        </h1>

        <p class="mt-4 text-slate-300">
          Dynamiskt laddad version
          ${escapeHtml(state.bundle.contentVersion)}.
          ${items.length} publicerade objekt.
        </p>
      </div>
    </header>

    <main class="mx-auto max-w-7xl px-6 py-8">
      <section
        class="-mt-14 rounded-3xl bg-white p-5 shadow-panel"
        aria-label="Filtrera innehåll"
      >
        <label class="block text-sm font-bold" for="search">
          Sök i lärinnehållet
        </label>

        <input
          id="search"
          class="mt-2 w-full rounded-xl border px-4 py-3
                 focus:border-aws focus:outline-none"
          type="search"
          value="${escapeHtml(state.query)}"
          placeholder="Sök på begrepp, beskrivning, ID eller tagg..."
        >

        <div class="mt-4 flex flex-wrap gap-2">
          ${groupPills}
        </div>

        <select
          id="tag-filter"
          class="mt-4 rounded-lg border px-3 py-2 text-sm"
          aria-label="Filtrera på tagg"
        >
          ${tagOptions}
        </select>
      </section>

      <p
        class="mb-4 mt-8 text-sm text-slate-500"
        aria-live="polite"
      >
        ${filtered.length} träffar
      </p>

      <section class="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        ${cards}
      </section>
    </main>

    <footer class="border-t bg-white">
      <div
        class="mx-auto flex max-w-7xl justify-between px-6 py-6
               text-sm text-slate-500"
      >
        <span>AWS Learning Curve</span>
        <span>JSON via HTTP GET • JavaScript • Tailwind CSS</span>
      </div>
    </footer>

    ${renderDetail(state.selected)}
  `;

  bindEvents();
}

function bindEvents() {
  document.querySelector("#search")?.addEventListener("input", (event) => {
    state.query = event.target.value;
    render();
    document.querySelector("#search")?.focus();
  });

  document
    .querySelector("#tag-filter")
    ?.addEventListener("change", (event) => {
      state.tag = event.target.value;
      render();
    });

  document.querySelectorAll("[data-group]").forEach((button) => {
    button.addEventListener("click", () => {
      state.group = button.dataset.group;
      render();
    });
  });

  document.querySelectorAll("[data-open-id]").forEach((button) => {
    button.addEventListener("click", () => {
      state.selected = allItems().find(
        (item) => item.id === button.dataset.openId
      );
      render();
    });
  });

  document.querySelector("#close-detail")?.addEventListener("click", () => {
    state.selected = null;
    render();
  });

  document
    .querySelector("#detail-backdrop")
    ?.addEventListener("mousedown", (event) => {
      if (event.target === event.currentTarget) {
        state.selected = null;
        render();
      }
    });
}

async function start() {
  const controller = new AbortController();

  try {
    const manifest = await getJson(
      "learning-bundle.manifest.json",
      controller.signal
    );

    const bundle = await getJson(
      "learning-bundle.json",
      controller.signal,
      manifest.contentVersion
    );

    state.manifest = manifest;
    state.bundle = bundle;

    render();
  } catch (error) {
    if (error.name === "AbortError") {
      return;
    }

    document.querySelector("#app").innerHTML = `
      <main class="mx-auto max-w-3xl p-6">
        <div
          class="rounded-2xl border border-red-200 bg-red-50 p-6
                 text-red-800"
        >
          <h1 class="text-xl font-bold">
            Data kunde inte hämtas
          </h1>

          <p class="mt-2">
            ${escapeHtml(error.message)}
          </p>

          <button
            id="reload"
            type="button"
            class="mt-4 underline"
          >
            Försök igen
          </button>
        </div>
      </main>
    `;

    document.querySelector("#reload")?.addEventListener("click", () => {
      window.location.reload();
    });
  }
}

start();
