// ============================================================
// Sozlamalar
// ============================================================
// Frontend endi backend bilan bitta domenda joylashgani uchun standart bo'sh qatorni
// (o'zi bilan bir xil domen) ishlatamiz. Agar frontendni alohida joyda (masalan GitHub
// Pages'da) sinasangiz, index.html'ga app.js'dan OLDIN shunday qator qo'shing:
//   <script>window.API_BASE_URL = "https://sizning-backend.onrender.com";</script>
const API_BASE = window.API_BASE_URL || "";
const MAX_PHOTOS = 4; // backend/app/routers/listings.py'dagi MAX_PHOTOS_PER_LISTING bilan mos

// ============================================================
// Telegram WebApp
// ============================================================
const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

// Lokal brauzerda (Telegramsiz) test qilish uchun zaxira initData
const initData = tg?.initData || "user=%7B%22id%22%3A111111%2C%22first_name%22%3A%22Test%22%7D&hash=dev";

// ============================================================
// Kunduzgi / tungi rejim
// ============================================================
const THEME_KEY = "autosavdo-theme";

function applyTheme(theme) {
  if (theme === "light") {
    document.documentElement.setAttribute("data-theme", "light");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  // Telegram Mini App'ning o'z sarlavha/fon rangini ham moslashtiramiz —
  // aks holda Telegram'ning tashqi paneli eski (tungi) rangda qolib ketardi.
  try {
    tg?.setHeaderColor(theme === "light" ? "#f4f6f9" : "#14161a");
    tg?.setBackgroundColor(theme === "light" ? "#f4f6f9" : "#14161a");
  } catch {
    // Eski Telegram klient versiyalarida bu metodlar bo'lmasligi mumkin
  }
}

applyTheme(localStorage.getItem(THEME_KEY) || "dark");

document.getElementById("btnTheme").addEventListener("click", () => {
  const next = document.documentElement.getAttribute("data-theme") === "light" ? "dark" : "light";
  localStorage.setItem(THEME_KEY, next);
  applyTheme(next);
});

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
  return "$" + new Intl.NumberFormat("en-US").format(n);
}
// Rasm manzili R2/CDN'dan to'liq URL ("https://...") yoki eski/lokal nisbiy
// yo'l ("/uploads/...") bo'lishi mumkin — faqat ikkinchi holatda API_BASE qo'shiladi.
function photoUrl(filePath) {
  return /^https?:\/\//.test(filePath) ? filePath : `${API_BASE}${filePath}`;
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
  // "create", "my" va "detail" sahifalarida pastki suzuvchi "E'lon berish"
  // tugmasi yashiriladi — bu sahifalarda o'zining ichki tugmalar qatori bor.
  document.getElementById("btnCreate").hidden = ["create", "my", "detail"].includes(name);
  window.scrollTo(0, 0);
}

document.querySelectorAll("[data-back]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    showView(btn.dataset.back);
    // Ro'yxat sahifasiga qaytilganda uni qayta yuklaymiz — aks holda
    // o'chirilgan/o'zgartirilgan e'lon eski (keshlangan) holatda ko'rinib qolardi.
    if (btn.dataset.back === "feed") {
      await loadFeed();
      // showView yuqoriga scroll qilib qo'yadi — oxirgi ochilgan e'lon
      // hali ham ro'yxatda bo'lsa, foydalanuvchini o'sha kartaga qaytaramiz.
      // Feed endi sahifalab (10 tadan) yuklangani uchun kerak bo'lsa, karta
      // topilguncha keyingi sahifalarni ham yuklaymiz.
      if (lastOpenedListingId != null) {
        const cardSelector = `.card[data-listing-id="${lastOpenedListingId}"]`;
        while (!document.querySelector(cardSelector) && feedHasMore) {
          await fetchFeedPage();
        }
        document.querySelector(cardSelector)?.scrollIntoView({ block: "center" });
      }
    }
  });
});

// ============================================================
// E'lon kartasi
// ============================================================
function renderCard(listing, { showStatus = false } = {}) {
  const cover = listing.photos?.[0];
  const div = document.createElement("div");
  div.className = "card";
  div.dataset.listingId = listing.id;
  div.innerHTML = `
    <div class="card__photo" style="${cover ? `background-image:url('${photoUrl(cover.file_path)}')` : ""}">
      ${cover ? "" : "Rasm yo'q"}
    </div>
    <div class="card__body">
      <div class="card__title">${listing.brand} ${listing.model}, ${listing.year}</div>
      <div class="card__price">${formatPrice(listing.price)}</div>
      <div class="card__meta">
        <span class="odo">${formatKm(listing.mileage)}</span>
        <span class="tag">${[listing.district, listing.region].filter(Boolean).join(", ")}</span>
        <span class="views" data-views-count>👁 ${listing.views_count || 0}</span>
      </div>
      ${showStatus ? `<span class="status-dot status-dot--${listing.status}">${STATUS_LABELS[listing.status]}</span>` : ""}
    </div>
  `;
  div.addEventListener("click", () => openDetail(listing.id));
  return div;
}

// ============================================================
// FEED (sahifalab, infinity scroll + "Ko'proq ko'rsatish" bilan)
// ============================================================
// Har safar 10 tadan yuklanadi. Ketma-ket 60 ta e'lon infinity scroll orqali
// yuklangach, avtomatik yuklash to'xtaydi va "Ko'proq ko'rsatish" tugmasi
// chiqadi — shunda server ortiqcha yuklanib ketmaydi. Tugma bosilganda
// navbatdagi 10 tasi yuklanib, infinity scroll yana keyingi 60 tagacha davom etadi.
const FEED_PAGE_SIZE = 10;
const FEED_AUTO_LOAD_LIMIT = 60;

let feedOffset = 0;
let feedLoading = false;
let feedHasMore = true;
let feedSegmentCount = 0; // joriy davrda infinity scroll orqali yuklangan e'lonlar soni

function feedParams() {
  const params = new URLSearchParams();
  const search = document.getElementById("fSearch").value.trim();
  if (search) params.set("search", search);
  return params;
}

async function fetchFeedPage() {
  if (feedLoading || !feedHasMore) return;
  feedLoading = true;

  const grid = document.getElementById("listingGrid");
  const empty = document.getElementById("feedEmpty");
  const loadMoreBtn = document.getElementById("btnLoadMore");

  const params = feedParams();
  const searchValue = params.get("search");
  params.set("limit", FEED_PAGE_SIZE);
  params.set("offset", feedOffset);

  try {
    const listings = await api(`/api/listings?${params.toString()}`);

    if (feedOffset === 0 && !listings.length) {
      empty.querySelector("p").innerHTML = searchValue
        ? "Siz kiritgan parametrlar bo'yicha e'lon topilmadi"
        : "Hozircha e'lon yo'q.<br/>Birinchi bo'lib joylang!";
      empty.hidden = false;
    } else {
      empty.hidden = true;
      listings.forEach((l) => grid.appendChild(renderCard(l)));
    }

    feedOffset += listings.length;
    feedSegmentCount += listings.length;
    if (listings.length < FEED_PAGE_SIZE) feedHasMore = false;

    loadMoreBtn.hidden = !feedHasMore || feedSegmentCount < FEED_AUTO_LOAD_LIMIT;
  } catch (e) {
    showToast(e.message);
  } finally {
    feedLoading = false;
  }
}

async function loadFeed() {
  feedOffset = 0;
  feedHasMore = true;
  feedSegmentCount = 0;
  feedLoading = false;
  document.getElementById("listingGrid").innerHTML = "";
  document.getElementById("btnLoadMore").hidden = true;
  await fetchFeedPage();
}

document.getElementById("btnFilter").addEventListener("click", loadFeed);

document.getElementById("btnLoadMore").addEventListener("click", () => {
  feedSegmentCount = 0;
  document.getElementById("btnLoadMore").hidden = true;
  fetchFeedPage();
});

// Ro'yxat oxiriga yaqinlashganda avtomatik keyingi sahifani yuklaydi — faqat
// joriy 60 talik davr tugamagan va feed ko'rinishi ochiq bo'lsa.
window.addEventListener("scroll", () => {
  if (views.feed.hidden) return;
  if (feedLoading || !feedHasMore) return;
  if (feedSegmentCount >= FEED_AUTO_LOAD_LIMIT) return;
  if (window.innerHeight + window.scrollY < document.body.offsetHeight - 300) return;
  fetchFeedPage();
});

// ============================================================
// DETAIL
// ============================================================
let lastOpenedListingId = null;

async function openDetail(id) {
  lastOpenedListingId = id;
  showView("detail");
  const content = document.getElementById("detailContent");
  content.innerHTML = "<p>Yuklanmoqda...</p>";

  try {
    const l = await api(`/api/listings/${id}`);
    const me = await api("/api/auth/me", { method: "POST" });
    const isOwner = me.id === l.user_id;

    // Kartalar ro'yxati qayta yuklanmasa ham, ko'rishlar sonini darhol yangilaymiz
    document.querySelectorAll(`.card[data-listing-id="${l.id}"] [data-views-count]`).forEach((el) => {
      el.textContent = `👁 ${l.views_count}`;
    });

    const gallery = l.photos?.length
      ? `<div class="detail-gallery">${l.photos.map((p) => `<img src="${photoUrl(p.file_path)}" />`).join("")}</div>`
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
        <div class="spec"><div class="spec__label">Shahar/tuman</div><div class="spec__value">${l.district || "—"}</div></div>
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
document.getElementById("btnCreateFromMy").addEventListener("click", () => showView("create"));
document.getElementById("btnCreateFromDetail").addEventListener("click", () => showView("create"));

// ============================================================
// Hudud / Shahar-tuman (bog'liq dropdownlar)
// ============================================================
let REGIONS_DATA = {};
const regionSelect = document.getElementById("cRegion");
const districtSelect = document.getElementById("cDistrict");

function resetDistrictSelect() {
  districtSelect.innerHTML = '<option value="">Avval hududni tanlang</option>';
  districtSelect.disabled = true;
}

api("/api/regions")
  .then((data) => {
    REGIONS_DATA = data;
    Object.keys(REGIONS_DATA).forEach((region) => {
      const opt = document.createElement("option");
      opt.value = region;
      opt.textContent = region;
      regionSelect.appendChild(opt);
    });
  })
  .catch(() => {});

regionSelect.addEventListener("change", () => {
  const districts = REGIONS_DATA[regionSelect.value] || [];
  if (!districts.length) {
    resetDistrictSelect();
    return;
  }
  districtSelect.disabled = false;
  districtSelect.innerHTML =
    '<option value="">Tanlang</option>' +
    districts.map((d) => `<option value="${d}">${d}</option>`).join("");
});

// ============================================================
// Marka (live search)
// ============================================================
let CAR_BRANDS_DATA = [];
const brandInput = document.getElementById("cBrand");
const brandList = document.getElementById("cBrandList");
let brandActiveIndex = -1;

api("/api/car-brands")
  .then((data) => {
    CAR_BRANDS_DATA = data;
  })
  .catch(() => {});

function hideBrandList() {
  brandList.hidden = true;
  brandList.innerHTML = "";
  brandActiveIndex = -1;
}

function renderBrandList(matches) {
  brandActiveIndex = -1;
  if (!matches.length) {
    hideBrandList();
    return;
  }
  brandList.innerHTML = matches
    .map((name) => `<li data-value="${name}">${name}</li>`)
    .join("");
  brandList.hidden = false;
}

function updateBrandActive(items) {
  items.forEach((li, i) => li.classList.toggle("active", i === brandActiveIndex));
  items[brandActiveIndex]?.scrollIntoView({ block: "nearest" });
}

brandInput.addEventListener("input", () => {
  const query = brandInput.value.trim().toLowerCase();
  if (!query) {
    hideBrandList();
    return;
  }
  const startsWith = CAR_BRANDS_DATA.filter((b) => b.toLowerCase().startsWith(query));
  const contains = CAR_BRANDS_DATA.filter(
    (b) => !b.toLowerCase().startsWith(query) && b.toLowerCase().includes(query)
  );
  renderBrandList([...startsWith, ...contains].slice(0, 8));
});

brandList.addEventListener("click", (e) => {
  const li = e.target.closest("li[data-value]");
  if (!li) return;
  brandInput.value = li.dataset.value;
  hideBrandList();
});

brandInput.addEventListener("keydown", (e) => {
  if (brandList.hidden) return;
  const items = [...brandList.querySelectorAll("li")];
  if (e.key === "ArrowDown") {
    e.preventDefault();
    brandActiveIndex = Math.min(brandActiveIndex + 1, items.length - 1);
    updateBrandActive(items);
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    brandActiveIndex = Math.max(brandActiveIndex - 1, 0);
    updateBrandActive(items);
  } else if (e.key === "Enter") {
    if (brandActiveIndex >= 0 && items[brandActiveIndex]) {
      e.preventDefault();
      brandInput.value = items[brandActiveIndex].dataset.value;
      hideBrandList();
    }
  } else if (e.key === "Escape") {
    hideBrandList();
  }
});

document.addEventListener("click", (e) => {
  if (!e.target.closest(".autocomplete")) hideBrandList();
});

// Foydalanuvchi kiritayotgan raqamni minglik bo'laklarga ajratib ko'rsatadi
// (masalan "5287400" -> "5 287 400"), shu bilan birga kursor pozitsiyasini saqlaydi.
function attachThousandsFormatter(input) {
  input.addEventListener("input", () => {
    const digitsBeforeCursor = input.value.slice(0, input.selectionStart).replace(/\D/g, "").length;
    const digits = input.value.replace(/\D/g, "");
    input.value = digits ? new Intl.NumberFormat("uz-UZ").format(Number(digits)) : "";

    let pos = 0;
    let count = 0;
    while (pos < input.value.length && count < digitsBeforeCursor) {
      if (/\d/.test(input.value[pos])) count++;
      pos++;
    }
    input.setSelectionRange(pos, pos);
  });
}
attachThousandsFormatter(document.getElementById("cMileage"));
attachThousandsFormatter(document.getElementById("cPrice"));

document.getElementById("createForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);

  const photoInput = document.getElementById("photoInput");
  if (photoInput.files.length > MAX_PHOTOS) {
    showToast(`Ko'pi bilan ${MAX_PHOTOS} ta rasm yuklash mumkin`);
    return;
  }

  const submitBtn = form.querySelector(".submit-btn");
  const submitLabel = submitBtn.querySelector(".submit-btn__label");
  submitBtn.disabled = true;
  submitBtn.classList.add("submit-btn--loading");
  submitLabel.textContent = "Yuborilmoqda...";

  const payload = {
    brand: fd.get("brand"),
    model: fd.get("model"),
    year: Number(fd.get("year")),
    mileage: Number(String(fd.get("mileage")).replace(/\D/g, "")),
    price: Number(String(fd.get("price")).replace(/\D/g, "")),
    transmission: fd.get("transmission") || null,
    fuel_type: fd.get("fuel_type") || null,
    region: fd.get("region") || null,
    district: fd.get("district") || null,
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

    // Rasmlar yuklab bo'lingandan keyin chaqiramiz — shunda adminga
    // yuboriladigan xabarda ular ham (kollaj holida) ko'rinadi.
    try {
      await api(`/api/listings/${listing.id}/submit`, { method: "POST" });
    } catch (submitErr) {
      // E'lon va rasmlar allaqachon saqlangan — admin xabari yetib bormasa ham
      // foydalanuvchiga xatolik ko'rsatmaymiz, e'lon baribir ko'rib chiqiladi.
    }

    if (failedNames.length) {
      showToast(`E'lon yuborildi, lekin ${failedNames.length} ta rasm yuklanmadi: ${failedNames.join(", ")}`);
    } else {
      showToast("E'lon yuborildi! Admin tasdiqlagach ro'yxatda ko'rinadi.");
    }
    form.reset();
    resetDistrictSelect();
    hideBrandList();
    showView("my");
    loadMyListings();
  } catch (e) {
    showToast(e.message);
  } finally {
    submitBtn.disabled = false;
    submitBtn.classList.remove("submit-btn--loading");
    submitLabel.textContent = "E'lonni joylash";
  }
});

// ============================================================
// Ishga tushirish
// ============================================================
loadFeed();
