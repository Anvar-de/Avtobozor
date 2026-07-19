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
const CURRENCY_LABELS = { USD: "$", UZS: "so'm" };
const PRICE_PLACEHOLDERS = { USD: "12 000", UZS: "120 000 000" };
// backend/app/schemas.py'dagi MAX_PRICE_BY_CURRENCY bilan mos bo'lishi shart.
const MAX_PRICE_BY_CURRENCY = { USD: 300_000, UZS: 4_000_000_000 };
function formatPrice(n, currency = "USD") {
  if (currency === "UZS") return new Intl.NumberFormat("uz-UZ").format(n) + " so'm";
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
// Foydalanuvchi kiritgan matnni (brand, model, tavsif va h.k.) innerHTML'ga
// qo'yishdan oldin tozalaydi — aks holda e'lon matni ichiga yashiringan
// <img onerror=...> kabi teglar boshqa foydalanuvchilar brauzerida ishga tushib
// qolishi mumkin edi (stored XSS).
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]
  ));
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
  const hideBottomBtns = ["create", "my", "detail"].includes(name);
  document.getElementById("btnCreate").hidden = hideBottomBtns;
  document.getElementById("btnRefreshFeed").hidden = hideBottomBtns;
  window.scrollTo(0, 0);
}

document.querySelectorAll("[data-back]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    // "Yangi e'lon" formasidan tahrirlashni yakunlamasdan chiqib ketilsa,
    // forma keyingi safar "yaratish" rejimida ochilishi uchun tozalaymiz.
    resetCreateFormState();
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
      <div class="card__title">${escapeHtml(listing.brand)} ${escapeHtml(listing.model)}, ${listing.year}</div>
      <div class="card__price">${formatPrice(listing.price, listing.currency)}</div>
      <div class="card__row">
        <span class="odo">${formatKm(listing.mileage)}</span>
      </div>
      <div class="card__row card__meta">
        <span class="tag">${[listing.district, listing.region].filter(Boolean).map(escapeHtml).join(", ")}</span>
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
// "Qidirish" tugmasi ketma-ket bir necha marta bosilsa, har bir bosish o'zining
// fetchFeedPage() so'rovini yuboradi — eski so'rov hali javob kutayotgan bo'lishi
// mumkin. Har bir loadFeed() chaqiruvida bu hisoblagich oshiriladi va oldingi
// (eskirgan) so'rov javobi kelganda uni e'tiborsiz qoldirib, natijalar
// takrorlanib qo'shilib ketishining (va offset noto'g'ri hisoblanishining) oldi olinadi.
let feedRequestId = 0;

// Raqamli filtr maydonidan (minglik ajratkichlar bilan formatlangan bo'lishi
// mumkin) tozalangan butun sonni oladi, bo'sh bo'lsa null qaytaradi.
function numericFieldValue(id) {
  const digits = document.getElementById(id).value.replace(/\D/g, "");
  return digits ? digits : null;
}

function feedParams() {
  const params = new URLSearchParams();
  const search = document.getElementById("fSearch").value.trim();
  if (search) params.set("search", search);

  const yearMin = document.getElementById("fYearMin").value.trim();
  const yearMax = document.getElementById("fYearMax").value.trim();
  if (yearMin) params.set("min_year", yearMin);
  if (yearMax) params.set("max_year", yearMax);

  const mileageMin = numericFieldValue("fMileageMin");
  const mileageMax = numericFieldValue("fMileageMax");
  if (mileageMin) params.set("min_mileage", mileageMin);
  if (mileageMax) params.set("max_mileage", mileageMax);

  const priceMin = numericFieldValue("fPriceMin");
  const priceMax = numericFieldValue("fPriceMax");
  if (priceMin) params.set("min_price", priceMin);
  if (priceMax) params.set("max_price", priceMax);
  // Backend shu valyutadagi oraliqni boshqa valyutaga o'girib, ikkalasini ham
  // qidiradi (bir xil kurs asosida) — narxning o'zi hech qachon o'zgartirilmaydi.
  if (priceMin || priceMax) {
    params.set("price_currency", document.getElementById("fCurrencyMin").dataset.currency);
  }

  return params;
}

// ============================================================
// Qidiruvning "qo'shimcha parametrlar" (slider) bo'limi
// ============================================================
const advancedFiltersEl = document.getElementById("advancedFilters");
const btnAdvancedToggle = document.getElementById("btnAdvancedToggle");
btnAdvancedToggle.addEventListener("click", () => {
  const isOpen = advancedFiltersEl.classList.toggle("advanced-filters--open");
  btnAdvancedToggle.classList.toggle("search-box__adv-btn--active", isOpen);
  btnAdvancedToggle.setAttribute("aria-expanded", String(isOpen));
});

async function fetchFeedPage() {
  if (feedLoading || !feedHasMore) return;
  feedLoading = true;
  const requestId = feedRequestId;

  const grid = document.getElementById("listingGrid");
  const empty = document.getElementById("feedEmpty");
  const loadMoreBtn = document.getElementById("btnLoadMore");

  const params = feedParams();
  const searchValue = params.get("search");
  params.set("limit", FEED_PAGE_SIZE);
  params.set("offset", feedOffset);

  try {
    const listings = await api(`/api/listings?${params.toString()}`);
    if (requestId !== feedRequestId) return; // shu orada yangi qidiruv boshlangan — eskirgan javob

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
    if (requestId === feedRequestId) showToast(e.message);
  } finally {
    if (requestId === feedRequestId) feedLoading = false;
  }
}

async function loadFeed() {
  feedRequestId++;
  feedOffset = 0;
  feedHasMore = true;
  feedSegmentCount = 0;
  feedLoading = false;
  document.getElementById("listingGrid").innerHTML = "";
  document.getElementById("btnLoadMore").hidden = true;
  await fetchFeedPage();
}

document.getElementById("btnFilter").addEventListener("click", () => {
  // Qidirish boshlanganda qo'shimcha parametrlar bo'limini yopamiz — foydalanuvchi
  // natijalarni ko'rishi kerak, forma ochiq turishi shart emas.
  advancedFiltersEl.classList.remove("advanced-filters--open");
  btnAdvancedToggle.classList.remove("search-box__adv-btn--active");
  btnAdvancedToggle.setAttribute("aria-expanded", "false");
  loadFeed();
});

document.getElementById("btnRefreshFeed").addEventListener("click", () => {
  // Qidiruv parametrlarini tozalab, ro'yxatni boshidan yuklaymiz.
  document.getElementById("fSearch").value = "";
  document.getElementById("fYearMin").value = "";
  document.getElementById("fYearMax").value = "";
  document.getElementById("fMileageMin").value = "";
  document.getElementById("fMileageMax").value = "";
  document.getElementById("fPriceMin").value = "";
  document.getElementById("fPriceMax").value = "";
  advancedFiltersEl.classList.remove("advanced-filters--open");
  btnAdvancedToggle.classList.remove("search-box__adv-btn--active");
  btnAdvancedToggle.setAttribute("aria-expanded", "false");
  loadFeed();
});

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
  const editWrap = document.getElementById("detailEditWrap");
  const deleteWrap = document.getElementById("detailDeleteWrap");
  content.innerHTML = "<p>Yuklanmoqda...</p>";
  editWrap.innerHTML = "";
  deleteWrap.innerHTML = "";

  try {
    const l = await api(`/api/listings/${id}`);
    const me = await api("/api/auth/me", { method: "POST" });
    const isOwner = me.id === l.user_id;
    // Admin egasi bo'lishidan qat'iy nazar istalgan e'lonni o'chira oladi.
    const canDelete = isOwner || me.is_admin;

    // Kartalar ro'yxati qayta yuklanmasa ham, ko'rishlar sonini darhol yangilaymiz
    document.querySelectorAll(`.card[data-listing-id="${l.id}"] [data-views-count]`).forEach((el) => {
      el.textContent = `👁 ${l.views_count}`;
    });

    const gallery = l.photos?.length
      ? `<div class="detail-gallery">${l.photos.map((p, i) => `<img src="${photoUrl(p.file_path)}" data-index="${i}" />`).join("")}</div>`
      : `<div class="detail-gallery--empty">Rasm yo'q</div>`;

    content.innerHTML = `
      ${gallery}
      <div class="detail-title">${escapeHtml(l.brand)} ${escapeHtml(l.model)}</div>
      <div class="detail-price">${formatPrice(l.price, l.currency)}</div>
      <div class="detail-specs">
        <div class="spec"><div class="spec__label">Yili</div><div class="spec__value">${l.year}</div></div>
        <div class="spec"><div class="spec__label">Probeg</div><div class="spec__value">${formatKm(l.mileage)}</div></div>
        <div class="spec"><div class="spec__label">Uzatma</div><div class="spec__value">${l.transmission ? escapeHtml(l.transmission) : "—"}</div></div>
        <div class="spec"><div class="spec__label">Yoqilg'i</div><div class="spec__value">${l.fuel_type ? escapeHtml(l.fuel_type) : "—"}</div></div>
        <div class="spec"><div class="spec__label">Hudud</div><div class="spec__value">${l.region ? escapeHtml(l.region) : "—"}</div></div>
        <div class="spec"><div class="spec__label">Shahar/tuman</div><div class="spec__value">${l.district ? escapeHtml(l.district) : "—"}</div></div>
        <div class="spec"><div class="spec__label">Holati</div><div class="spec__value">${STATUS_LABELS[l.status]}</div></div>
      </div>
      ${l.description ? `<div class="detail-desc">${escapeHtml(l.description)}</div>` : ""}
      ${
        !isOwner && l.contact_phone
          ? `<a class="contact-btn" href="tel:${escapeHtml(l.contact_phone)}">📞 Sotuvchiga qo'ng'iroq qilish</a>`
          : ""
      }
    `;

    editWrap.innerHTML = me.is_admin
      ? `<button class="edit-btn" id="editListing">
           <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M12 20h9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
           Tahrirlash
         </button>`
      : "";

    deleteWrap.innerHTML = canDelete
      ? `<button class="delete-btn" id="deleteListing">
           <svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M3 6h18" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 11v6M14 11v6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
           ${isOwner ? "O'chirish" : "O'chirish (admin)"}
         </button>`
      : "";

    if (l.photos?.length) {
      content.querySelectorAll(".detail-gallery img").forEach((img) => {
        img.addEventListener("click", () => openLightbox(l.photos, Number(img.dataset.index)));
      });
    }

    if (me.is_admin) {
      document.getElementById("editListing")?.addEventListener("click", () => openEditForm(l));
    }
    if (canDelete) {
      document.getElementById("deleteListing")?.addEventListener("click", async () => {
        if (!confirm("E'lonni o'chirishga ishonchingiz komilmi?")) return;
        try {
          await api(`/api/listings/${id}`, { method: "DELETE" });
          showToast("E'lon o'chirildi");
          if (isOwner) {
            showView("my");
            loadMyListings();
          } else {
            showView("feed");
            loadFeed();
          }
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
// LIGHTBOX (rasmni to'liq ekranda ko'rish)
// ============================================================
const lightboxEl = document.getElementById("lightbox");
const lightboxImgEl = document.getElementById("lightboxImg");
const lightboxPrevEl = document.getElementById("lightboxPrev");
const lightboxNextEl = document.getElementById("lightboxNext");
let lightboxPhotos = [];
let lightboxIndex = 0;

function renderLightbox() {
  lightboxImgEl.src = photoUrl(lightboxPhotos[lightboxIndex].file_path);
  const hasMultiple = lightboxPhotos.length > 1;
  lightboxPrevEl.classList.toggle("lightbox__nav--hidden", !hasMultiple);
  lightboxNextEl.classList.toggle("lightbox__nav--hidden", !hasMultiple);
}

function openLightbox(photos, index) {
  lightboxPhotos = photos;
  lightboxIndex = index;
  renderLightbox();
  lightboxEl.classList.add("lightbox--visible");
}

function closeLightbox() {
  lightboxEl.classList.remove("lightbox--visible");
}

lightboxEl.addEventListener("click", (e) => {
  if (e.target === lightboxEl) closeLightbox();
});
lightboxImgEl.addEventListener("click", closeLightbox);
document.getElementById("lightboxClose").addEventListener("click", closeLightbox);
lightboxPrevEl.addEventListener("click", () => {
  lightboxIndex = (lightboxIndex - 1 + lightboxPhotos.length) % lightboxPhotos.length;
  renderLightbox();
});
lightboxNextEl.addEventListener("click", () => {
  lightboxIndex = (lightboxIndex + 1) % lightboxPhotos.length;
  renderLightbox();
});
document.addEventListener("keydown", (e) => {
  if (!lightboxEl.classList.contains("lightbox--visible")) return;
  if (e.key === "Escape") closeLightbox();
  if (e.key === "ArrowLeft") lightboxPrevEl.click();
  if (e.key === "ArrowRight") lightboxNextEl.click();
});

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
// YANGI E'LON / TAHRIRLASH
// ============================================================
// null bo'lsa — forma yangi e'lon yaratish uchun; aks holda shu ID'dagi
// e'lon tahrirlanmoqda (faqat admin uchun, backend shuni talab qiladi).
let editingListingId = null;

function resetCreateFormState() {
  editingListingId = null;
  document.getElementById("createFormTitle").textContent = "Yangi e'lon";
  document.getElementById("createFormHint").textContent = "E'lon joylashdan oldin admin tomonidan ko'rib chiqiladi.";
  document.getElementById("photoField").hidden = false;
  document.getElementById("btnSubmitCreate").querySelector(".submit-btn__label").textContent = "E'lonni joylash";
}

function startCreateFlow() {
  resetCreateFormState();
  document.getElementById("createForm").reset();
  resetDistrictSelect();
  // form.reset() faqat name= atributli maydonlarni tozalaydi — valyuta tugmasi
  // alohida holat sifatida saqlangani uchun standart holatga qo'lda qaytariladi.
  document.getElementById("cCurrencyToggle").dataset.currency = "USD";
  document.getElementById("cCurrencyToggle").textContent = CURRENCY_LABELS.USD;
  document.getElementById("cPrice").placeholder = PRICE_PLACEHOLDERS.USD;
  showView("create");
}

// Faqat admin uchun: mavjud e'lonni "Yangi e'lon" formasi orqali tahrirlaydi.
// Rasm maydoni yashiriladi — bu forma faqat matn/raqam maydonlarini yangilaydi.
function openEditForm(listing) {
  const form = document.getElementById("createForm");
  form.reset();
  editingListingId = listing.id;

  form.brand.value = listing.brand || "";
  form.model.value = listing.model || "";
  form.year.value = listing.year || "";
  document.getElementById("cMileage").value = listing.mileage ? new Intl.NumberFormat("uz-UZ").format(listing.mileage) : "";
  document.getElementById("cPrice").value = listing.price ? new Intl.NumberFormat("uz-UZ").format(listing.price) : "";
  const currency = listing.currency || "USD";
  document.getElementById("cCurrencyToggle").dataset.currency = currency;
  document.getElementById("cCurrencyToggle").textContent = CURRENCY_LABELS[currency];
  document.getElementById("cPrice").placeholder = PRICE_PLACEHOLDERS[currency];
  form.transmission.value = listing.transmission || "";
  form.fuel_type.value = listing.fuel_type || "";
  form.region.value = listing.region || "";
  regionSelect.dispatchEvent(new Event("change"));
  form.district.value = listing.district || "";
  form.contact_phone.value = listing.contact_phone || "";
  form.description.value = listing.description || "";

  document.getElementById("createFormTitle").textContent = "E'lonni tahrirlash";
  document.getElementById("createFormHint").textContent = "O'zgarishlar saqlangach, e'lon darhol yangilanadi.";
  document.getElementById("photoField").hidden = true;
  document.getElementById("btnSubmitCreate").querySelector(".submit-btn__label").textContent = "Saqlash";
  showView("create");
}

document.getElementById("btnCreate").addEventListener("click", startCreateFlow);
document.getElementById("btnCreateFromMy").addEventListener("click", startCreateFlow);
document.getElementById("btnCreateFromDetail").addEventListener("click", startCreateFlow);

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
// `getMax` berilsa, foydalanuvchi shu chegaradan katta son kirita olmaydi —
// qiymat chegaraga avtomatik qisqartiriladi (masalan narx maydonida valyutaga
// mos maksimal narxdan oshirib yozib bo'lmasin deb).
function attachThousandsFormatter(input, getMax) {
  input.addEventListener("input", () => {
    const digitsBeforeCursor = input.value.slice(0, input.selectionStart).replace(/\D/g, "").length;
    let digits = input.value.replace(/\D/g, "");
    const max = getMax?.();
    if (max != null && digits && Number(digits) > max) {
      digits = String(max);
    }
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
attachThousandsFormatter(
  document.getElementById("cPrice"),
  () => MAX_PRICE_BY_CURRENCY[document.getElementById("cCurrencyToggle").dataset.currency]
);
attachThousandsFormatter(document.getElementById("fMileageMin"));
attachThousandsFormatter(document.getElementById("fMileageMax"));
attachThousandsFormatter(document.getElementById("fPriceMin"));
attachThousandsFormatter(document.getElementById("fPriceMax"));

// ============================================================
// Narx maydonlaridagi "$ / so'm" valyuta tugmasi
// ============================================================
// E'lon berish formasi: bitta maydon, bitta tugma. Valyuta almashtirilganda
// avvalgi kiritilgan raqam ma'nosiz bo'lib qolmasligi uchun maydon tozalanadi
// (masalan so'mda "200 000 000" kiritilgan bo'lsa, dollarga o'tkazilganda shu
// raqamning o'zi qolib ketmasligi kerak).
const cCurrencyToggle = document.getElementById("cCurrencyToggle");
cCurrencyToggle.addEventListener("click", () => {
  const next = cCurrencyToggle.dataset.currency === "USD" ? "UZS" : "USD";
  cCurrencyToggle.dataset.currency = next;
  cCurrencyToggle.textContent = CURRENCY_LABELS[next];
  const priceInput = document.getElementById("cPrice");
  priceInput.value = "";
  priceInput.placeholder = PRICE_PLACEHOLDERS[next];
});

// Qidiruv filtri: "dan" va "gacha" ikkalasida ham tugma bor, lekin ular bitta
// umumiy valyuta holatini boshqaradi — qaysi birida bossa ham ikkalasi ham
// birga almashadi, ikkalasi ham tozalanadi.
const fCurrencyMin = document.getElementById("fCurrencyMin");
const fCurrencyMax = document.getElementById("fCurrencyMax");
function setSearchPriceCurrency(next) {
  [fCurrencyMin, fCurrencyMax].forEach((btn) => {
    btn.dataset.currency = next;
    btn.textContent = CURRENCY_LABELS[next];
  });
  document.getElementById("fPriceMin").value = "";
  document.getElementById("fPriceMax").value = "";
}
fCurrencyMin.addEventListener("click", () => setSearchPriceCurrency(fCurrencyMin.dataset.currency === "USD" ? "UZS" : "USD"));
fCurrencyMax.addEventListener("click", () => setSearchPriceCurrency(fCurrencyMax.dataset.currency === "USD" ? "UZS" : "USD"));

document.getElementById("createForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = e.target;
  const fd = new FormData(form);

  const payload = {
    brand: fd.get("brand"),
    model: fd.get("model"),
    year: Number(fd.get("year")),
    mileage: Number(String(fd.get("mileage")).replace(/\D/g, "")),
    price: Number(String(fd.get("price")).replace(/\D/g, "")),
    currency: cCurrencyToggle.dataset.currency,
    transmission: fd.get("transmission") || null,
    fuel_type: fd.get("fuel_type") || null,
    region: fd.get("region") || null,
    district: fd.get("district") || null,
    description: fd.get("description") || null,
    contact_phone: fd.get("contact_phone") || null,
  };

  const maxPrice = MAX_PRICE_BY_CURRENCY[payload.currency];
  if (payload.price > maxPrice) {
    showToast(`Narx ${new Intl.NumberFormat("uz-UZ").format(maxPrice)} ${CURRENCY_LABELS[payload.currency]} dan katta bo'lmasligi kerak`);
    return;
  }

  const submitBtn = document.getElementById("btnSubmitCreate");
  const submitLabel = submitBtn.querySelector(".submit-btn__label");

  // Tahrirlash rejimi (faqat admin uchun) — yangi e'lon yaratish/rasm
  // yuklash oqimidan butunlay boshqacha, oddiy PATCH so'rovi kifoya.
  if (editingListingId) {
    const id = editingListingId;
    submitBtn.disabled = true;
    submitBtn.classList.add("submit-btn--loading");
    submitLabel.textContent = "Saqlanmoqda...";
    try {
      await api(`/api/listings/${id}`, { method: "PATCH", body: payload });
      showToast("E'lon yangilandi");
      resetCreateFormState();
      showView("detail");
      openDetail(id);
    } catch (err) {
      showToast(err.message);
    } finally {
      submitBtn.disabled = false;
      submitBtn.classList.remove("submit-btn--loading");
      submitLabel.textContent = editingListingId ? "Saqlash" : "E'lonni joylash";
    }
    return;
  }

  const photoInput = document.getElementById("photoInput");
  if (photoInput.files.length === 0) {
    showToast("Kamida 1 ta rasm yuklashingiz kerak");
    return;
  }
  if (photoInput.files.length > MAX_PHOTOS) {
    showToast(`Ko'pi bilan ${MAX_PHOTOS} ta rasm yuklash mumkin`);
    return;
  }

  submitBtn.disabled = true;
  submitBtn.classList.add("submit-btn--loading");
  submitLabel.textContent = "Yuborilmoqda...";

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
