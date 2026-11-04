const API = "";

let currentPage = 1;
const pageSize = 20;
let currentSearch = "";
let selectedIds = new Set();
let activeCustomer = null;

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[m]));
}

function showToast(message, type = "normal") {
  const el = $("app-toast");
  el.textContent = message;
  el.style.background = type === "error" ? "#b91c1c" : "#0f172a";
  el.classList.add("show");

  setTimeout(() => {
    el.classList.remove("show");
  }, 2800);
}

function openModal(id) {
  $(id).classList.add("open");
}

function closeModal(id) {
  $(id).classList.remove("open");
}


// ============================================================
// QUALITY SCORE
// ============================================================

function qualityScore(c) {
  const fields = [
    "name",
    "email",
    "phone",
    "address",
    "dob"
  ];

  const filled = fields.filter(
    field =>
      c?.[field] !== null &&
      c?.[field] !== undefined &&
      String(c[field]).trim() !== ""
  ).length;

  return Math.round(
    (filled / fields.length) * 100
  );
}


// ============================================================
// SOURCE LABELS
// ============================================================

function sourceLabel(source) {

  const map = {
    SourceA: "Core Banking",
    SourceB: "Credit Card",
    SourceC: "Loan System",
    "Data Steward": "Data Steward",
    "Data Steward Override": "Data Steward"
  };

  return map[source] || source || "System";
}


function sourceBadgeClass(source) {

  if (source === "SourceB") {
    return "badge-cc";
  }

  if (source === "SourceC") {
    return "badge-loan";
  }

  if (String(source || "").includes("Steward")) {
    return "badge-override";
  }

  return "badge-core";
}


// ============================================================
// API HELPER
// ============================================================

async function apiFetch(url, options = {}) {

  const res = await fetch(
    API + url,
    options
  );

  let data = {};

  try {
    data = await res.json();
  } catch {
    data = {};
  }

  if (!res.ok) {

    throw new Error(
      data.detail ||
      data.message ||
      `Request failed (${res.status})`
    );
  }

  return data;
}


// ============================================================
// DASHBOARD
// ============================================================

async function loadDashboard() {

  try {

    const data = await apiFetch(
      "/api/dashboard/stats"
    );

    $("kpi-golden").textContent =
      Number(
        data.golden_records ??
        data.total_golden_records ??
        0
      ).toLocaleString();

    $("kpi-source").textContent =
      `From ${
        Number(
          data.source_records ??
          data.source_customers ??
          data.total_source_records ??
          0
        ).toLocaleString()
      } source records`;

    $("kpi-matched").textContent =
      Number(
        data.matched_groups ?? 0
      ).toLocaleString();

    $("kpi-singletons").textContent =
      `${
        Number(
          data.singleton_groups ??
          data.singletons ??
          0
        ).toLocaleString()
      } singleton records`;

    $("kpi-links").textContent =
      Number(
        data.match_links ?? 0
      ).toLocaleString();

    $("kpi-transactions").textContent =
      Number(
        data.linked_transactions ??
        data.transactions ??
        0
      ).toLocaleString();

    $("kpi-linkage").textContent =
      `${
        Number(
          data.linkage_rate ?? 0
        ).toFixed(2)
      }% linkage rate`;

  } catch (err) {

    console.error(err);

    showToast(
      "Dashboard statistics could not be loaded.",
      "error"
    );
  }
}


// ============================================================
// CUSTOMER LIST
// ============================================================

async function loadCustomers(page = 1) {

  try {

    currentPage = page;

    let data;

    // --------------------------------------------------------
    // Search
    // --------------------------------------------------------

    if (currentSearch) {

      data = await apiFetch(
        `/api/customers/search?q=${encodeURIComponent(currentSearch)}`
      );

      const customers =
        data.customers || [];

      renderCustomers(customers);

      renderPagination(
        customers.length,
        1,
        1
      );

      return;
    }


    // --------------------------------------------------------
    // Normal pagination
    // --------------------------------------------------------

    const offset =
      (page - 1) * pageSize;

    data = await apiFetch(
      `/api/customers?limit=${pageSize}&offset=${offset}`
    );

    const customers =
      data.customers || [];

    renderCustomers(customers);

    const count =
      Number(
        data.count ??
        customers.length
      );

    // Backend currently returns page-sized
    // count rather than a total count.

    const hasNext =
      customers.length === pageSize;

    renderPagination(
      offset + customers.length,
      page,
      hasNext ? page + 1 : page
    );

    $("btn-next").disabled =
      !hasNext;

    $("btn-prev").disabled =
      page <= 1;

  } catch (err) {

    console.error(err);

    $("customer-table-body").innerHTML =
      "";

    $("table-empty-state").hidden =
      false;

    showToast(
      "Could not load customer records.",
      "error"
    );
  }
}


// ============================================================
// RENDER CUSTOMER TABLE
// ============================================================

function renderCustomers(customers) {

  const tbody =
    $("customer-table-body");

  tbody.innerHTML = "";

  if (!customers.length) {

    $("table-empty-state").hidden =
      false;

    updateSelectionUI();

    return;
  }

  $("table-empty-state").hidden =
    true;


  customers.forEach(c => {

    const id =
      c.golden_id;

    const score =
      qualityScore(c);

    const checked =
      selectedIds.has(id)
        ? "checked"
        : "";

    const tr =
      document.createElement("tr");

    tr.innerHTML = `

      <td class="checkbox-col">

        <input
          type="checkbox"
          class="customer-checkbox"
          value="${escapeHtml(id)}"
          ${checked}
        >

      </td>


      <td>

        <span class="badge badge-master">

          ${escapeHtml(id)}

        </span>

      </td>


      <td>

        <strong>
          ${escapeHtml(
            c.name || "Unknown"
          )}
        </strong>

      </td>


      <td>

        ${escapeHtml(
          c.email || "—"
        )}

      </td>


      <td>

        ${escapeHtml(
          c.phone || "—"
        )}

      </td>


      <td>

        <span class="badge ${
          Number(
            c.match_group_size || 1
          ) > 1
            ? "badge-cc"
            : "badge-core"
        }">

          ${
            Number(
              c.match_group_size || 1
            )
          }

          record${
            Number(
              c.match_group_size || 1
            ) === 1
              ? ""
              : "s"
          }

        </span>

      </td>


      <td>

        <div class="quality-wrap">

          <div class="quality-bar">

            <div
              class="quality-fill"
              style="width:${score}%"
            ></div>

          </div>

          <span class="quality-number">

            ${score}%

          </span>

        </div>

      </td>


      <td class="text-right">

        <button
          class="btn btn-sm btn-secondary view-btn"
          data-id="${escapeHtml(id)}"
        >

          View 360°

        </button>

      </td>

    `;

    tbody.appendChild(tr);

  });


  // ----------------------------------------------------------
  // Checkbox events
  // ----------------------------------------------------------

  tbody
    .querySelectorAll(
      ".customer-checkbox"
    )
    .forEach(cb => {

      cb.addEventListener(
        "change",
        () => {

          if (cb.checked) {

            selectedIds.add(
              cb.value
            );

          } else {

            selectedIds.delete(
              cb.value
            );
          }

          updateSelectionUI();

        }
      );

    });


  // ----------------------------------------------------------
  // View buttons
  // ----------------------------------------------------------

  tbody
    .querySelectorAll(
      ".view-btn"
    )
    .forEach(btn => {

      btn.addEventListener(
        "click",
        () =>
          viewCustomer360(
            btn.dataset.id
          )
      );

    });


  updateSelectionUI();
}


// ============================================================
// PAGINATION
// ============================================================

function renderPagination(
  shown,
  page,
  totalPages
) {

  $("pagination-info").textContent =
    `Showing ${
      shown.toLocaleString()
    } records on this page`;

  $("page-label").textContent =
    `Page ${page}`;

  $("btn-prev").disabled =
    page <= 1;

  $("btn-next").disabled =
    page >= totalPages;
}


// ============================================================
// CUSTOMER 360
// ============================================================

async function viewCustomer360(
  goldenId
) {

  try {

    const data =
      await apiFetch(
        `/api/customers/${encodeURIComponent(goldenId)}`
      );

    activeCustomer =
      data;

    const gr =
      data.golden_record || {};

    const sources =
      data.source_records?.records || [];

    const txns =
      data.transactions?.records || [];


    $("m-name").textContent =
      gr.name ||
      "Unknown Customer";

    $("m-golden-id").textContent =
      gr.golden_id ||
      goldenId;


    const score =
      qualityScore(gr);

    $("m-quality").textContent =
      `${score}% Quality`;


    // --------------------------------------------------------
    // Avatar initials
    // --------------------------------------------------------

    const initials =
      String(
        gr.name || "CU"
      )
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map(
          x => x[0]
        )
        .join("")
        .toUpperCase();

    $("m-avatar").textContent =
      initials || "CU";


    // --------------------------------------------------------
    // Source systems
    // --------------------------------------------------------

    const systemNames =
      [
        ...new Set(
          sources.map(s => {

            const sid =
              s.source_id;

            return sourceLabel(
              sid === 1
                ? "SourceA"
                : sid === 2
                ? "SourceB"
                : sid === 3
                ? "SourceC"
                : String(sid)
            );

          })
        )
      ];


    $("m-systems").innerHTML =
      systemNames
        .map(
          s => `
            <span
              class="badge ${
                s.includes("Credit")
                  ? "badge-cc"
                  : s.includes("Loan")
                  ? "badge-loan"
                  : "badge-core"
              }"
            >

              ${escapeHtml(s)}

            </span>
          `
        )
        .join("");


    $("m-txn-count").textContent =
      txns.length;

    $("m-source-count").textContent =
      sources.length;


    fillGoldenRecord(gr);

    fillTransactions(txns);

    fillSources(sources);


    switchTab(
      "tab-overview"
    );

    openModal(
      "c360-modal"
    );

  } catch (err) {

    console.error(err);

    showToast(
      err.message,
      "error"
    );
  }
}


// ============================================================
// GOLDEN RECORD
// ============================================================

function fillGoldenRecord(gr) {

  const values = {

    name:
      gr.name,

    email:
      gr.email,

    phone:
      gr.phone,

    dob:
      gr.dob,

    address:
      gr.address

  };


  Object.entries(
    values
  ).forEach(
    ([field, value]) => {

      $(
        `val-${field}`
      ).textContent =
        value || "—";


      const source =
        gr[
          `${field}_source`
        ];


      const trace =
        $(
          `trace-${field}`
        );


      trace.textContent =
        sourceLabel(source);


      trace.className =
        `source-trace-badge ${
          sourceBadgeClass(
            source
          )
        }`;

    }
  );


  document
    .querySelectorAll(
      ".btn-override"
    )
    .forEach(btn => {

      btn.onclick =
        () =>
          openEditModal(
            btn.dataset.field
          );

    });
}


// ============================================================
// TRANSACTIONS
// ============================================================

function fillTransactions(
  txns
) {

  const tbody =
    $("transactions-container");

  tbody.innerHTML =
    "";


  if (!txns.length) {

    tbody.innerHTML = `

      <tr>

        <td
          colspan="5"
          class="empty-state"
        >

          No transactions linked.

        </td>

      </tr>

    `;

    return;
  }


  txns.forEach(t => {

    const amount =
      Number(
        t.amount || 0
      );

    const type =
      String(
        t.transaction_type || ""
      ).toLowerCase();

    const positive =
      type.includes("credit") ||
      amount >= 0;


    const tr =
      document.createElement("tr");


    tr.innerHTML = `

      <td>

        <code>
          ${escapeHtml(
            t.txn_id
          )}
        </code>

      </td>


      <td>

        <code>
          ${escapeHtml(
            t.account_id
          )}
        </code>

      </td>


      <td>

        ${escapeHtml(
          t.transaction_date ||
          "—"
        )}

      </td>


      <td>

        ${escapeHtml(
          t.transaction_type ||
          "—"
        )}

      </td>


      <td
        class="text-right ${
          positive
            ? "amount-credit"
            : "amount-debit"
        }"
      >

        ${
          amount.toLocaleString(
            undefined,
            {
              minimumFractionDigits: 2,
              maximumFractionDigits: 2
            }
          )
        }

      </td>

    `;


    tbody.appendChild(
      tr
    );

  });
}

// ============================================================
// SOURCE RECORDS + MATCH EXPLANATION
// ============================================================

function fillSources(sources) {

  const container =
    $("source-records-container");

  container.innerHTML = "";

  if (!sources.length) {

    container.innerHTML = `
      <div class="empty-state">
        No source records found.
      </div>
    `;

    return;
  }


  sources.forEach(s => {

    // --------------------------------------------------------
    // SOURCE NAME
    // --------------------------------------------------------

    const sourceName =
      s.source_id === 1
        ? "SourceA"
        : s.source_id === 2
        ? "SourceB"
        : s.source_id === 3
        ? "SourceC"
        : String(
            s.source_id ||
            "Unknown"
          );


    // --------------------------------------------------------
    // MATCH METHOD
    // --------------------------------------------------------

    const method =
      String(
        s.match_method || ""
      ).toUpperCase();


    let matchTitle = "No Match";

    let matchDescription =
      "This is the original source record for this Golden Record.";

    let matchIcon = "⚪";

    let matchColor = "#64748b";

    let matchBackground = "#f8fafc";

    let matchScoreText = "N/A";


    // --------------------------------------------------------
    // DIRECT EMAIL MATCH
    // --------------------------------------------------------

    if (
      method === "EXACT_EMAIL" ||
      method.includes("EMAIL")
    ) {

      matchTitle =
        "Direct Match — Email";

      matchDescription =
        "Customer matched using an exact email address.";

      matchIcon = "🟢";

      matchColor = "#15803d";

      matchBackground = "#f0fdf4";

    }


    // --------------------------------------------------------
    // DIRECT PHONE MATCH
    // --------------------------------------------------------

    else if (
      method === "EXACT_PHONE" ||
      method.includes("PHONE")
    ) {

      matchTitle =
        "Direct Match — Phone";

      matchDescription =
        "Customer matched using an exact phone number.";

      matchIcon = "🟢";

      matchColor = "#15803d";

      matchBackground = "#f0fdf4";

    }


    // --------------------------------------------------------
    // FUZZY NAME + ADDRESS MATCH
    // --------------------------------------------------------

    else if (
      method === "FUZZY_NAME_ADDRESS" ||
      method.includes("FUZZY")
    ) {

      matchTitle =
        "Fuzzy Match — Name + Address";

      matchDescription =
        "Customer matched using similarity between name and address.";

      matchIcon = "🟡";

      matchColor = "#b45309";

      matchBackground = "#fffbeb";

    }


    // --------------------------------------------------------
    // OTHER MATCH TYPES
    // --------------------------------------------------------

    else if (method) {

      matchTitle =
        method.replaceAll("_", " ");

      matchDescription =
        "Customer matched using the MDM matching engine.";

      matchIcon = "🔵";

      matchColor = "#1d4ed8";

      matchBackground = "#eff6ff";

    }


    // --------------------------------------------------------
    // MATCH SCORE
    // --------------------------------------------------------

    if (
      s.match_score !== null &&
      s.match_score !== undefined &&
      s.match_score !== ""
    ) {

      const numericScore =
        Number(s.match_score);

      if (!Number.isNaN(numericScore)) {

        matchScoreText =
          `${(numericScore * 100).toFixed(0)}%`;

      }

    }


    // --------------------------------------------------------
    // SOURCE CARD
    // --------------------------------------------------------

    const card =
      document.createElement("div");

    card.className =
      "source-record-card";


    card.innerHTML = `

      <!-- SOURCE HEADER -->

      <div
        class="source-card-header"
        style="
          display:flex;
          justify-content:space-between;
          align-items:center;
          gap:12px;
        "
      >

        <div>

          <strong>
            ${escapeHtml(
              sourceLabel(sourceName)
            )}
          </strong>

          <div
            style="
              margin-top:4px;
              font-size:12px;
              color:#64748b;
            "
          >
            Source Customer ID:
            <strong>
              ${escapeHtml(
                s.source_customer_id || "—"
              )}
            </strong>
          </div>

        </div>


        <span
          class="badge ${
            sourceBadgeClass(sourceName)
          }"
        >
          ${escapeHtml(sourceName)}
        </span>

      </div>


      <!-- MATCH INFORMATION -->

      <div
        style="
          margin-top:16px;
          padding:14px 16px;
          border-radius:10px;
          background:${matchBackground};
          border:1px solid ${matchColor}33;
        "
      >

        <div
          style="
            display:flex;
            justify-content:space-between;
            align-items:center;
            gap:12px;
          "
        >

          <div
            style="
              display:flex;
              align-items:center;
              gap:8px;
              font-weight:700;
              color:${matchColor};
            "
          >

            <span>
              ${matchIcon}
            </span>

            <span>
              ${escapeHtml(matchTitle)}
            </span>

          </div>


          <span
            style="
              font-weight:700;
              color:${matchColor};
            "
          >
            ${escapeHtml(matchScoreText)}
          </span>

        </div>


        <div
          style="
            margin-top:7px;
            font-size:12px;
            color:#475569;
            line-height:1.5;
          "
        >
          ${escapeHtml(matchDescription)}
        </div>


        ${
          method === "FUZZY_NAME_ADDRESS"
            ? `
              <div
                style="
                  margin-top:8px;
                  font-size:11px;
                  color:#92400e;
                  font-weight:600;
                "
              >
                Matching threshold: 85%
              </div>
            `
            : ""
        }

      </div>


      <!-- SOURCE FIELDS -->

      <div
        class="source-fields"
        style="margin-top:16px;"
      >

        <div class="source-field">

          <span>
            Name
          </span>

          <strong>
            ${escapeHtml(
              s.name || "—"
            )}
          </strong>

        </div>


        <div class="source-field">

          <span>
            Email
          </span>

          <strong>
            ${escapeHtml(
              s.email || "—"
            )}
          </strong>

        </div>


        <div class="source-field">

          <span>
            Phone
          </span>

          <strong>
            ${escapeHtml(
              s.phone || "—"
            )}
          </strong>

        </div>


        <div class="source-field">

          <span>
            DOB
          </span>

          <strong>
            ${escapeHtml(
              s.dob || "—"
            )}
          </strong>

        </div>


        <div
          class="source-field"
          style="grid-column:1/-1"
        >

          <span>
            Address
          </span>

          <strong>
            ${escapeHtml(
              s.address || "—"
            )}
          </strong>

        </div>

      </div>

    `;


    container.appendChild(card);

  });

}

// ============================================================
// EDIT GOLDEN RECORD
// ============================================================

function openEditModal(
  field
) {

  if (
    !activeCustomer?.golden_record
  ) {
    return;
  }


  const gr =
    activeCustomer.golden_record;

  const goldenId =
    gr.golden_id;


  $("edit-golden-id").value =
    goldenId;

  $("edit-field").value =
    field;

  $("edit-id-display").value =
    goldenId;

  $("edit-field-display").value =
    field.toUpperCase();

  $("edit-current").value =
    gr[field] ?? "";

  $("edit-new-value").value =
    gr[field] ?? "";


  openModal(
    "edit-modal"
  );
}


async function saveEdit() {

  const goldenId =
    $("edit-golden-id").value;

  const field =
    $("edit-field").value;

  const value =
    $("edit-new-value")
      .value
      .trim();

  const changedBy =
    $("edit-changed-by")
      .value
      .trim() ||
    "Data Steward";

  const reason =
    $("edit-reason")
      .value
      .trim() ||
    "Manual customer data correction";


  if (!value) {

    showToast(
      "New value is required.",
      "error"
    );

    return;
  }


  try {

    await apiFetch(
      `/api/customers/${encodeURIComponent(goldenId)}`,
      {
        method: "PATCH",

        headers: {
          "Content-Type":
            "application/json"
        },

        body:
          JSON.stringify({
            [field]: value,
            changed_by:
              changedBy,
            reason:
              reason
          })
      }
    );


    closeModal(
      "edit-modal"
    );


    showToast(
      `${field.toUpperCase()} updated successfully.`
    );


    await viewCustomer360(
      goldenId
    );

    await loadCustomers(
      currentPage
    );

    await loadDashboard();

  } catch (err) {

    showToast(
      err.message,
      "error"
    );
  }
}


// ============================================================
// BULK UPDATE
// ============================================================

function updateSelectionUI() {

  const count =
    selectedIds.size;

  $("selected-count").textContent =
    count;

  $("selection-bar").hidden =
    count === 0;


  const visibleBoxes =
    [
      ...document.querySelectorAll(
        ".customer-checkbox"
      )
    ];


  $("select-all").checked =
    visibleBoxes.length > 0 &&
    visibleBoxes.every(
      cb => cb.checked
    );
}


async function bulkUpdate() {

  const ids =
    [...selectedIds];

  const field =
    $("bulk-field").value;

  const value =
    $("bulk-value")
      .value
      .trim();


  if (!ids.length) {

    showToast(
      "Select at least one customer.",
      "error"
    );

    return;
  }


  if (!value) {

    showToast(
      "Enter a new value.",
      "error"
    );

    return;
  }


  try {

    const result =
      await apiFetch(
        "/api/customers/bulk-update",
        {
          method: "PATCH",

          headers: {
            "Content-Type":
              "application/json"
          },

          body:
            JSON.stringify({

              golden_ids:
                ids,

              field:
                field,

              value:
                value,

              changed_by:
                "Data Steward",

              reason:
                "Bulk customer data correction"

            })
        }
      );


    selectedIds.clear();

    $("bulk-value").value =
      "";

    updateSelectionUI();


    showToast(
      `${
        result.updated_count ??
        ids.length
      } customer(s) updated.`
    );


    await loadCustomers(
      currentPage
    );

    await loadDashboard();

  } catch (err) {

    showToast(
      err.message,
      "error"
    );
  }
}


// ============================================================
// AUDIT
// ============================================================

async function openAudit() {

  try {

    const data =
      await apiFetch(
        "/api/audit?limit=100"
      );

    const logs =
      data.logs || [];

    const tbody =
      $("audit-table-body");

    tbody.innerHTML =
      "";


    if (!logs.length) {

      tbody.innerHTML = `

        <tr>

          <td
            colspan="7"
            class="empty-state"
          >

            No audit records found.

          </td>

        </tr>

      `;

    } else {

      logs.forEach(log => {

        const oldValue =
          extractAuditValue(
            log.old_value
          );

        const newValue =
          extractAuditValue(
            log.new_value
          );

        const field =
          extractAuditField(
            log.old_value,
            log.new_value
          );


        const tr =
          document.createElement(
            "tr"
          );


        tr.innerHTML = `

          <td>

            ${
              escapeHtml(
                log.created_at
                  ? new Date(
                      log.created_at
                    ).toLocaleString()
                  : "—"
              )
            }

          </td>


          <td>

            <code>

              ${escapeHtml(
                log.entity_id ||
                "—"
              )}

            </code>

          </td>


          <td>

            <strong>

              ${escapeHtml(
                field
              )}

            </strong>

          </td>


          <td>

            ${escapeHtml(
              oldValue
            )}

          </td>


          <td>

            ${escapeHtml(
              newValue
            )}

          </td>


          <td>

            ${escapeHtml(
              log.changed_by ||
              "—"
            )}

          </td>


          <td>

            ${escapeHtml(
              log.reason ||
              ""
            )}

          </td>

        `;


        tbody.appendChild(
          tr
        );

      });

    }


    openModal(
      "audit-modal"
    );

  } catch (err) {

    console.error(err);

    showToast(
      err.message ||
      "Could not load audit records.",
      "error"
    );
  }
}


function extractAuditField(
  oldObj,
  newObj
) {

  const obj =
    oldObj ||
    newObj ||
    {};


  if (
    typeof obj !==
    "object"
  ) {
    return "—";
  }


  return Object.keys(
    obj
  ).find(
    k =>
      k !== "_reason" &&
      k !== "value"
  ) || "—";
}


function extractAuditValue(
  obj
) {

  if (
    obj === null ||
    obj === undefined
  ) {
    return "—";
  }


  if (
    typeof obj !==
    "object"
  ) {
    return String(obj);
  }


  if (
    Object.prototype.hasOwnProperty.call(
      obj,
      "value"
    )
  ) {

    return String(
      obj.value ??
      "—"
    );
  }


  const keys =
    Object.keys(obj)
      .filter(
        k =>
          k !== "_reason"
      );


  return keys.length
    ? String(
        obj[keys[0]] ??
        "—"
      )
    : "—";
}


// ============================================================
// CSV IMPORT
// ============================================================

async function uploadCsv() {

  const file =
    $("upload-file")
      .files[0];

  const sourceName =
    $("upload-source")
      .value;


  if (!file) {

    showToast(
      "Select a CSV file first.",
      "error"
    );

    return;
  }


  const formData =
    new FormData();


  formData.append(
    "source_name",
    sourceName
  );

  formData.append(
    "file",
    file
  );


  $("upload-status").textContent =
    `Uploading ${file.name}...`;


  try {

    const result =
      await apiFetch(
        "/api/import/csv",
        {
          method: "POST",
          body: formData
        }
      );


    $("upload-status").textContent =
      `Imported ${
        result.imported_count ??
        result.rows_imported ??
        0
      } records successfully.`;


    showToast(
      "CSV imported successfully."
    );


    await loadDashboard();

    await loadCustomers(
      1
    );


    setTimeout(
      () =>
        closeModal(
          "upload-modal"
        ),
      1200
    );

  } catch (err) {

    $("upload-status").textContent =
      `Error: ${err.message}`;

    showToast(
      err.message,
      "error"
    );
  }
}


// ============================================================
// MANUAL SOURCE CUSTOMER
// ============================================================

async function saveCustomer() {

  const payload = {

    source_name:
      $("customer-source")
        .value,

    source_customer_id:
      $("customer-source-id")
        .value
        .trim(),

    name:
      $("customer-name")
        .value
        .trim() ||
      null,

    email:
      $("customer-email")
        .value
        .trim() ||
      null,

    phone:
      $("customer-phone")
        .value
        .trim() ||
      null,

    dob:
      $("customer-dob")
        .value ||
      null,

    address:
      $("customer-address")
        .value
        .trim() ||
      null

  };


  if (
    !payload.source_customer_id
  ) {

    showToast(
      "Source Customer ID is required.",
      "error"
    );

    return;
  }


  try {

    // FastAPI expects
    // multipart/form-data.

    const formData =
      new FormData();


    formData.append(
      "source_name",
      payload.source_name ||
      ""
    );

    formData.append(
      "source_customer_id",
      payload.source_customer_id ||
      ""
    );

    formData.append(
      "name",
      payload.name ||
      ""
    );

    formData.append(
      "email",
      payload.email ||
      ""
    );

    formData.append(
      "phone",
      payload.phone ||
      ""
    );

    formData.append(
      "dob",
      payload.dob ||
      ""
    );

    formData.append(
      "address",
      payload.address ||
      ""
    );


    const result =
      await apiFetch(
        "/api/customers/upload",
        {
          method: "POST",

          // DO NOT manually set
          // Content-Type here.
          // Browser adds the
          // multipart boundary.

          body: formData
        }
      );


    $("customer-upload-status")
      .textContent =
        result.message ||
        "Customer uploaded successfully.";


    showToast(
      "Customer data saved."
    );


    $("customer-form")
      .reset();


    await loadDashboard();

    await loadCustomers(
      1
    );


    setTimeout(
      () =>
        closeModal(
          "customer-modal"
        ),
      1000
    );

  } catch (err) {

    console.error(err);

    $("customer-upload-status")
      .textContent =
        `Error: ${err.message}`;

    showToast(
      err.message,
      "error"
    );
  }
}


// ============================================================
// TABS
// ============================================================

function switchTab(
  tabId
) {

  document
    .querySelectorAll(
      ".tab-btn"
    )
    .forEach(btn => {

      btn.classList.toggle(
        "active",
        btn.dataset.tab ===
          tabId
      );

    });


  document
    .querySelectorAll(
      ".tab-pane"
    )
    .forEach(pane => {

      pane.classList.toggle(
        "active",
        pane.id === tabId
      );

    });
}


// ============================================================
// EVENTS
// ============================================================

let searchTimer;


// ------------------------------------------------------------
// Search
// ------------------------------------------------------------

$("search-input")
  .addEventListener(
    "input",
    (e) => {

      currentSearch =
        e.target.value.trim();

      $("clear-search").hidden =
        !currentSearch;


      clearTimeout(
        searchTimer
      );


      searchTimer =
        setTimeout(
          () =>
            loadCustomers(
              1
            ),
          300
        );

    }
  );


// ------------------------------------------------------------
// Clear search
// ------------------------------------------------------------

$("clear-search")
  .addEventListener(
    "click",
    () => {

      $("search-input")
        .value = "";

      currentSearch =
        "";

      $("clear-search")
        .hidden = true;

      loadCustomers(
        1
      );

    }
  );


// ------------------------------------------------------------
// Select all
// ------------------------------------------------------------

$("select-all")
  .addEventListener(
    "change",
    (e) => {

      document
        .querySelectorAll(
          ".customer-checkbox"
        )
        .forEach(cb => {

          cb.checked =
            e.target.checked;


          if (
            e.target.checked
          ) {

            selectedIds.add(
              cb.value
            );

          } else {

            selectedIds.delete(
              cb.value
            );

          }

        });


      updateSelectionUI();

    }
  );


// ------------------------------------------------------------
// Clear selection
// ------------------------------------------------------------

$("btn-clear-selection")
  .addEventListener(
    "click",
    () => {

      selectedIds.clear();


      document
        .querySelectorAll(
          ".customer-checkbox"
        )
        .forEach(
          cb =>
            cb.checked = false
        );


      $("select-all")
        .checked = false;


      updateSelectionUI();

    }
  );


// ------------------------------------------------------------
// Bulk update
// ------------------------------------------------------------

$("btn-bulk-update")
  .addEventListener(
    "click",
    bulkUpdate
  );


// ------------------------------------------------------------
// Previous page
// ------------------------------------------------------------

$("btn-prev")
  .addEventListener(
    "click",
    () => {

      if (
        currentPage > 1
      ) {

        loadCustomers(
          currentPage - 1
        );

      }

    }
  );


// ------------------------------------------------------------
// Next page
// ------------------------------------------------------------

$("btn-next")
  .addEventListener(
    "click",
    () => {

      loadCustomers(
        currentPage + 1
      );

    }
  );


// ------------------------------------------------------------
// Audit
// ------------------------------------------------------------

$("btn-view-audit")
  .addEventListener(
    "click",
    openAudit
  );


// ------------------------------------------------------------
// CSV upload modal
// ------------------------------------------------------------

$("btn-open-upload")
  .addEventListener(
    "click",
    () =>
      openModal(
        "upload-modal"
      )
  );


// ------------------------------------------------------------
// Manual customer modal
// ------------------------------------------------------------

$("btn-open-customer")
  .addEventListener(
    "click",
    () =>
      openModal(
        "customer-modal"
      )
  );


// ------------------------------------------------------------
// Customer 360 modal
// ------------------------------------------------------------

$("btn-close-c360")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "c360-modal"
      )
  );


$("btn-footer-close")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "c360-modal"
      )
  );


// ------------------------------------------------------------
// Edit modal
// ------------------------------------------------------------

$("btn-close-edit")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "edit-modal"
      )
  );


$("btn-cancel-edit")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "edit-modal"
      )
  );


$("btn-save-edit")
  .addEventListener(
    "click",
    saveEdit
  );


// ------------------------------------------------------------
// Audit modal
// ------------------------------------------------------------

$("btn-close-audit")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "audit-modal"
      )
  );


// ------------------------------------------------------------
// CSV import modal
// ------------------------------------------------------------

$("btn-close-upload")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "upload-modal"
      )
  );


$("btn-cancel-upload")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "upload-modal"
      )
  );


$("btn-submit-upload")
  .addEventListener(
    "click",
    uploadCsv
  );


// ------------------------------------------------------------
// Manual customer modal
// ------------------------------------------------------------

$("btn-close-customer")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "customer-modal"
      )
  );


$("btn-cancel-customer")
  .addEventListener(
    "click",
    () =>
      closeModal(
        "customer-modal"
      )
  );


$("btn-save-customer")
  .addEventListener(
    "click",
    saveCustomer
  );


// ------------------------------------------------------------
// Tabs
// ------------------------------------------------------------

document
  .querySelectorAll(
    ".tab-btn"
  )
  .forEach(btn => {

    btn.addEventListener(
      "click",
      () =>
        switchTab(
          btn.dataset.tab
        )
    );

  });


// ------------------------------------------------------------
// Close modal by clicking backdrop
// ------------------------------------------------------------

document
  .querySelectorAll(
    ".modal-backdrop"
  )
  .forEach(backdrop => {

    backdrop.addEventListener(
      "click",
      (e) => {

        if (
          e.target ===
          backdrop
        ) {

          backdrop.classList.remove(
            "open"
          );

        }

      }
    );

  });


// ============================================================
// INITIAL LOAD
// ============================================================

document.addEventListener(
  "DOMContentLoaded",
  async () => {

    await loadDashboard();

    await loadCustomers(
      1
    );

  }
);