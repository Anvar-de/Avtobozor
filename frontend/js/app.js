// ============================================================
// Sozlamalar
// ============================================================
// Frontend endi backend bilan bitta domenda joylashgani uchun standart bo'sh qatorni
// (o'zi bilan bir xil domen) ishlatamiz. Agar frontendni alohida joyda (masalan GitHub
// Pages'da) sinasangiz, index.html'ga app.js'dan OLDIN shunday qator qo'shing:
//   <script>window.API_BASE_URL = "https://sizning-backend.onrender.com";</script>
const API_BASE = window.API_BASE_URL || "";
const MAX_PHOTOS = 8; // backend/app/routers/listings.py'dagi MAX_PHOTOS_PER_LISTING bilan mos

// ============================================================
// Telegram WebApp
// ============================================================
const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

// Lokal brauzerda (Telegramsiz) test qilish uchun zaxira initData
const initData = tg?.initData || "user=%7B%22id%22%3A111111%2C%22first_name%22%3A%22Test%22%7D&hash=dev";

async function api(path, { method = "GET", body, isForm = false } = {}) {
  const headers = { "X-Telegram-Init-Data": initData };
  if (!isForm && body) headers["Content-Type"] = "application/json";

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Xatolik yuz berdi" }));
    let message = "Xatolik yuz berdi";
    if (typeof err.detail === "string") {
      message = err.detail;
    } else if (Array.isArray(err.detail)) {
      // FastAPI validatsiya xatolari ro'yxat ko'rinishida keladi
      message = err.detail
        .map((d) => (typeof d === "string" ? d : d.msg || "Noto'g'ri qiymat"))
        .join("; ");
    }
    throw new Error(message);
  }
  return res.status === 204 ? null : res.json();
}

// ============================================================
// Yordamchi funksiyalar
// ============================================================
function formatPrice(n) {
  return new Intl.NumberFormat("uz-UZ").format(n) + " so'm";
}
function formatKm(n) {
  return new Intl.NumberFormat("uz-UZ").format(n) + " km";
}

let toastTimer;
function showToast(msg) {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("toast--visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("toast--visible"), 2500);
}

const STATUS_LABELS = {
  pending: "Ko'rib chiqilmoqda",
  approved: "Faol",
  rejected: "Rad etilgan",
  sold: "Sotilgan",
};

// ============================================================
// Ko'rinishlarni almashtirish (routing)
// ============================================================
const views = {
  feed: document.getElementById("view-feed"),
  detail: document.getElementById("view-detail"),
  my: document.getElementById("view-my"),
  create: document.getElementById("view-create"),
};

function showView(name) {
  Object.entries(views).forEach(([key, el]) => (el.hidden = key !== name));
  window.scrollTo(0, 0);
}

document.querySelectorAll("[data-back]").forEach((btn) => {
  btn.addEventListener("click", () => showView(btn.dataset.back));
});

// ============================================================
// E'lon kartasi
// ============================================================
function renderCard(listing, { showStatus = false } = {}) {
  const cover = listing.photos?.[0];
  const div = document.createElement("div");
  div.className = "card";
  div.innerHTML = `
    <div class="card__photo" style="${cover ? `background-image:url('${API_BASE}${cover.file_path}')` : ""}">
      ${cover ? "" : "Rasm yo'q"}
    </div>
    <div class="card__body">
      <div class="card__title">${listing.brand} ${listing.model}, ${listing.year}</div>
      <div class="card__price">${formatPrice(listing.price)}</div>
      <div class="card__meta">
        <span class="odo">${formatKm(listing.mileage)}</span>
        <span class="tag">${listing.region || ""}</span>
      </div>
      ${showStatus ? `<span class="status-dot status-dot--${listing.status}">${STATUS_LABELS[listing.status]}</span>` : ""}
    </div>
  `;
  div.addEventListener("click", () => openDetail(listing.id));
  return div;
}

// ============================================================
// FEED
// ============================================================
async function loadFeed() {
  const grid = document.getElementById("listingGrid");
  const empty = document.getElementById("feedEmpty");
  grid.innerHTML = "";

  const params = new URLSearchParams();
  const brand = document.getElementById("fBrand").value.trim();
  const region = document.getElementById("fRegion").value.trim();
  const minYear = document.getElementById("fMinYear").value;
  const maxPrice = document.getElementById("fMaxPrice").value;
  if (brand) params.set("brand", brand);
  if (region) params.set("region", region);
  if (minYear) params.set("min_year", minYear);
  if (maxPrice) params.set("max_price", maxPrice);

  try {
    const listings = await api(`/api/listings?${params.toString()}`);
    if (!listings.length) {
      empty.hidden = false;
    } else {
      empty.hidden = true;
      listings.forEach((l) => grid.appendChild(renderCard(l)));
    }
  } catch (e) {
    showToast(e.message);
  }
}

document.getElementById("btnFilter").addEventListener("click", loadFeed);

// ============================================================
// DETAIL
// ============================================================
async function openDetail(id) {
  showView("detail");
  const content = document.getElementById("detailContent");
  content.innerHTML = "<p>Yuklanmoqda...</p>";

  try {
    const l = await api(`/api/listings/${id}`);
    const me = await api("/api/auth/me", { method: "POST" });
    const isOwner = me.id === l.user_id;

    const gallery = l.photos?.length
      ? `<div class="detail-gallery">${l.photos.map((p) => `<img src="${API_BASE}${p.file_path}" />`).join("")}</div>`
      : `<div class="detail-gallery--empty">Rasm yo'q</div>`;

    content.innerHTML = `
      ${gallery}
      <div class="detail-title">${l.brand} ${l.model}</div>
      <div class="detail-price">${formatPrice(l.price)}</div>
      <div class="detail-specs">
        <div class="spec"><div class="spec__label">Yili</div><div class="spec__value">${l.year}</div></div>
        <div class="spec"><div class="spec__label">Probeg</div><div class="spec__value">${formatKm(l.mileage)}</div></div>
        <div class="spec"><div class="spec__label">Uzatma</div><div class="spec__value">${l.transmission || "—"}</div></div>
        <div class="spec"><div class="spec__label">Yoqilg'i</div><div class="spec__value">${l.fuel_type || "—"}</div></div>
        <div class="spec"><div class="spec__label">Hudud</div><div class="spec__value">${l.region || "—"}</div></div>
        <div class="spec"><div class="spec__label">Holati</div><div class="spec__value">${STATUS_LABELS[l.status]}</div></div>
      </div>
      ${l.description ? `<div class="detail-desc">${l.description}</div>` : ""}
      ${
        isOwner
          ? `<div class="owner-actions">
               ${l.status !== "sold" ? `<button class="success" id="markSold">Sotildi deb belgilash</button>` : ""}
               <button class="danger" id="deleteListing">O'chirish</button>
             </div>`
          : l.contact_phone
          ? `<a class="contact-btn" href="tel:${l.contact_phone}">📞 Sotuvchiga qo'ng'iroq qilish</a>`
          : ""
      }
    `;

    if (isOwner) {
      document.getElementById("markSold")?.addEventListener("click", async () => {
        try {
          await api(`/api/listings/${id}`, { method: "PATCH", body: { status: "sold" } });
          showToast("E'lon sotilgan deb belgilandi");
          openDetail(id);
        } catch (e) {
          showToast(e.message);
        }
      });
      document.getElementById("deleteListing")?.addEventListener("click", async () => {
        if (!confirm("E'lonni o'chirishga ishonchingiz komilmi?")) return;
        try {
          await api(`/api/listings/${id}`, { method: "DELETE" });
          showToast("E'lon o'chirildi");
          showView("my");
          loadMyListings();
        } catch (e) {
          showToast(e.message);
        }
      });
    }
  } catch (e) {
    content.innerHTML = `<p>Xatolik: ${e.message}</p>`;
  }
}

// ============================================================
// MENING E'LONLARIM
// ============================================================
async function loadMyListings() {
  const grid = document.getElementById("myListingGrid");
  const empty = document.getElementById("myEmpty");
  grid.innerHTML = "";
  try {
    const listings = await api("/api/listings/my");
    if (!listings.length) {
      empty.hidden = false;
    } else {
      empty.hidden = true;
      listings.forEach((l) => grid.appendChild(renderCard(l, { showStatus: true })));
    }
  } catch (e) {
    showToast(e.message);
  }
}

document.getElementById("btnMyListings").addEventListener("click", () => {
  showView("my");
  loadMyListings();
});

// ============================================================
// YANGI E'LON
// ============================================================
document.getElementById("btnCreate").addEventListener("click", () => showView("create"));

document.getElementById("createForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);

  const photoInput = document.getElementById("photoInput");
  if (photoInput.files.length > MAX_PHOTOS) {
    showToast(`Ko'pi bilan ${MAX_PHOTOS} ta rasm yuklash mumkin`);
    return;
  }

  const payload = {
    brand: fd.get("brand"),
    model: fd.get("model"),
    year: Number(fd.get("year")),
    mileage: Number(fd.get("mileage")),
    price: Number(fd.get("price")),
    transmission: fd.get("transmission") || null,
    fuel_type: fd.get("fuel_type") || null,
    region: fd.get("region") || null,
    description: fd.get("description") || null,
    contact_phone: fd.get("contact_phone") || null,
  };

  try {
    const listing = await api("/api/listings", { method: "POST", body: payload });

    // Har bir faylni ALOHIDA try/catch bilan yuklaymiz — aks holda bitta buzuq
    // fayl (masalan noodatiy PNG) butun tsiklni to'xtatib, undan keyingi barcha
    // rasmlar serverga umuman yetib bormay qolardi.
    const failedNames = [];
    for (const file of photoInput.files) {
      try {
        const photoForm = new FormData();
        photoForm.append("file", file);
        await api(`/api/listings/${listing.id}/photos`, { method: "POST", body: photoForm, isForm: true });
      } catch (photoErr) {
        failedNames.push(file.name);
      }
    }

    if (failedNames.length) {
      showToast(`E'lon yuborildi, lekin ${failedNames.length} ta rasm yuklanmadi: ${failedNames.join(", ")}`);
    } else {
      showToast("E'lon yuborildi! Admin tasdiqlagach ro'yxatda ko'rinadi.");
    }
    form.reset();
    showView("my");
    loadMyListings();
  } catch (e) {
    showToast(e.message);
  }
});

// ============================================================
// Ishga tushirish
// ============================================================
loadFeed();
