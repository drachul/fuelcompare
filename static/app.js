(() => {
  "use strict";

  const vehiclesEl = document.getElementById("vehicles");
  const template = document.getElementById("vehicle-card-template");
  const errorBox = document.getElementById("error-box");
  const resultsEl = document.getElementById("results");
  let vehicleSeq = 0;
  let yearsCache = null;
  let savedVehiclesCache = null;

  async function fetchJSON(url, options) {
    const resp = await fetch(url, options);
    const data = await resp.json().catch(() => null);
    if (!resp.ok) {
      const message = (data && data.error) || `Request failed (${resp.status})`;
      throw new Error(message);
    }
    return data;
  }

  function showError(message) {
    if (!message) {
      errorBox.hidden = true;
      errorBox.textContent = "";
      return;
    }
    errorBox.hidden = false;
    errorBox.textContent = message;
  }

  const fuelTankCapModelAliases = {
    "ford:f150": "f-150",
    "ford:f250": "f-250",
    "ford:f350": "f-350",
    "ford:f450": "f-450",
  };

  function urlSlug(value) {
    return value
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/&/g, " and ")
      .replace(/['’]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "");
  }

  function fuelTankCapVehicleUrl(make, model, year) {
    const makeSlug = urlSlug(make || "");
    const simplifiedModel = (model || "")
      .replace(/\s+(?:pickup|cab chassis|2wd|4wd|awd|fwd|rwd)\b.*$/i, "")
      .trim();
    let modelSlug = urlSlug(simplifiedModel);
    modelSlug = fuelTankCapModelAliases[`${makeSlug}:${modelSlug}`] || modelSlug;
    if (!makeSlug || !modelSlug) return "https://fueltankcap.com/";
    const modelUrl = `https://fueltankcap.com/${makeSlug}/${modelSlug}`;
    return /^\d{4}$/.test(String(year || "")) ? `${modelUrl}/${year}` : modelUrl;
  }

  const priceLocation = document.getElementById("fuel-price-location");
  const loadFuelPricesButton = document.getElementById("load-fuel-prices");
  const fuelPriceNote = document.getElementById("fuel-price-note");
  const priceInputs = {
    regular: document.getElementById("price-regular"),
    midgrade: document.getElementById("price-midgrade"),
    premium: document.getElementById("price-premium"),
    diesel: document.getElementById("price-diesel"),
  };

  function setFuelPriceNote(message, sourceUrl) {
    fuelPriceNote.replaceChildren(document.createTextNode(message));
    if (sourceUrl) {
      const sourceLink = document.createElement("a");
      sourceLink.href = sourceUrl;
      sourceLink.target = "_blank";
      sourceLink.rel = "noopener";
      sourceLink.textContent = " View source.";
      fuelPriceNote.appendChild(sourceLink);
    }
  }

  function formatPeriod(period) {
    const [year, month] = period.split("-").map(Number);
    if (!year || !month) return period;
    return new Intl.DateTimeFormat(undefined, {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    })
      .format(new Date(Date.UTC(year, month - 1, 1)));
  }

  async function loadFuelPriceLocations() {
    try {
      const locations = await fetchJSON("/api/fuel-price-locations");
      fillSelect(priceLocation, locations, "Select Canada or a city");
      let savedLocation = "";
      try {
        savedLocation = localStorage.getItem("fuelPriceLocation") || "";
      } catch (_storageErr) {
        // Storage can be disabled; the lookup itself should still work.
      }
      if (savedLocation && locations.includes(savedLocation)) {
        priceLocation.value = savedLocation;
        loadFuelPricesButton.disabled = false;
      }
    } catch (_err) {
      resetSelect(priceLocation, "Location lookup unavailable");
      setFuelPriceNote("Statistics Canada lookup is unavailable. Enter prices manually or use the current-price link.");
    }
  }

  priceLocation.addEventListener("change", () => {
    loadFuelPricesButton.disabled = !priceLocation.value;
    if (priceLocation.value) {
      try {
        localStorage.setItem("fuelPriceLocation", priceLocation.value);
      } catch (_storageErr) {
        // Remembering the selection is optional.
      }
      setFuelPriceNote("Use the latest monthly average, or enter prices manually below.");
    }
  });

  loadFuelPricesButton.addEventListener("click", async () => {
    if (!priceLocation.value) return;
    loadFuelPricesButton.disabled = true;
    setFuelPriceNote("Loading the latest Statistics Canada averages…");
    try {
      const data = await fetchJSON(
        `/api/fuel-prices?location=${encodeURIComponent(priceLocation.value)}`
      );
      document.getElementById("price-unit").value = data.price_unit;
      for (const fuel of ["regular", "premium", "diesel"]) {
        if (Number.isFinite(data.prices[fuel])) {
          priceInputs[fuel].value = data.prices[fuel].toFixed(3);
        }
      }
      setFuelPriceNote(
        `${data.location}: ${formatPeriod(data.period)} average in CAD/L. ` +
        "Regular, premium, and diesel were updated; midgrade is not published and was left unchanged.",
        data.source_url
      );
    } catch (err) {
      setFuelPriceNote(`${err.message} Enter prices manually or use the current-price link.`);
    } finally {
      loadFuelPricesButton.disabled = !priceLocation.value;
    }
  });

  loadFuelPriceLocations();

  const splitSlider = document.getElementById("city-highway-slider");
  const cityWeightLabel = document.getElementById("city-weight-label");
  const highwayWeightLabel = document.getElementById("highway-weight-label");

  function updateSplitLabels() {
    const city = parseInt(splitSlider.value, 10);
    cityWeightLabel.textContent = `${city}% city`;
    highwayWeightLabel.textContent = `${100 - city}% highway`;
  }
  splitSlider.addEventListener("input", updateSplitLabels);
  updateSplitLabels();

  function resetSelect(select, placeholder) {
    select.innerHTML = `<option value="">${placeholder}</option>`;
    select.disabled = true;
  }

  function fillSelect(select, values, placeholder) {
    select.innerHTML = `<option value="">${placeholder}</option>`;
    for (const v of values) {
      const opt = document.createElement("option");
      opt.value = typeof v === "string" ? v : v.value;
      opt.textContent = typeof v === "string" ? v : v.text;
      select.appendChild(opt);
    }
    select.disabled = false;
  }

  async function ensureYears(select) {
    if (!yearsCache) {
      yearsCache = await fetchJSON("/api/years");
    }
    fillSelect(select, yearsCache, "Select year");
  }

  function populateSavedSelect(select, selectedValue = "") {
    const options = (savedVehiclesCache || []).map((vehicle) => ({
      value: String(vehicle.record_id),
      text: vehicle.label,
    }));
    fillSelect(select, options, options.length ? "Load a saved vehicle" : "No saved vehicles yet");
    select.disabled = options.length === 0;
    select.value = selectedValue;
  }

  async function ensureSavedVehicles(select) {
    if (!savedVehiclesCache) {
      savedVehiclesCache = await fetchJSON("/api/saved-vehicles");
    }
    populateSavedSelect(select);
  }

  async function refreshSavedVehicles() {
    savedVehiclesCache = await fetchJSON("/api/saved-vehicles");
    for (const select of document.querySelectorAll(".v-saved")) {
      populateSavedSelect(select, select.value);
    }
  }

  function addVehicleCard(defaultLabel) {
    const index = vehicleSeq++;
    const frag = template.content.cloneNode(true);
    const card = frag.querySelector(".vehicle-card");
    card.dataset.index = String(index);

    const labelEl = card.querySelector(".v-label");
    const placeholderLabel = defaultLabel || `Vehicle ${index + 1}`;
    let fallbackLabel = placeholderLabel;

    const savedSel = card.querySelector(".v-saved");
    const yearSel = card.querySelector(".v-year");
    const makeSel = card.querySelector(".v-make");
    const modelSel = card.querySelector(".v-model");
    const trimSel = card.querySelector(".v-trim");
    const cityInput = card.querySelector(".v-city");
    const highwayInput = card.querySelector(".v-highway");
    const fuelSel = card.querySelector(".v-fuel");
    const tankInput = card.querySelector(".v-tank");
    const tankUnitSel = card.querySelector(".v-tank-unit");
    const tankOptions = card.querySelector(".v-tank-options");
    const tankHint = card.querySelector(".v-tank-hint");
    const note = card.querySelector(".v-note");
    let vehicleLoadSeq = 0;

    const tankOptionsId = `tank-options-${index}`;
    tankOptions.id = tankOptionsId;
    tankInput.setAttribute("list", tankOptionsId);

    function setTankHint(message, manualLookupUrl = "") {
      tankHint.hidden = false;
      tankHint.replaceChildren(document.createTextNode(message));
      if (manualLookupUrl) {
        const lookupLink = document.createElement("a");
        lookupLink.href = manualLookupUrl;
        lookupLink.target = "_blank";
        lookupLink.rel = "noopener";
        lookupLink.textContent = " Look it up on FuelTankCap.";
        tankHint.appendChild(lookupLink);
      }
    }

    function clearTankLookup() {
      tankInput.value = "";
      tankUnitSel.value = "liter";
      tankOptions.replaceChildren();
      tankHint.hidden = true;
      tankHint.textContent = "";
    }

    function selectedText(select) {
      return select.value ? select.options[select.selectedIndex].text : "";
    }

    function updateLabel() {
      const year = selectedText(yearSel);
      const make = selectedText(makeSel);
      const model = selectedText(modelSel);
      const trim = selectedText(trimSel);
      if (year && make && model) {
        labelEl.textContent = trim ? `${year} ${make} ${model} — ${trim}` : `${year} ${make} ${model}`;
      } else {
        labelEl.textContent = fallbackLabel;
      }
    }
    updateLabel();

    ensureYears(yearSel).catch((err) => showError(err.message));
    ensureSavedVehicles(savedSel).catch(() => {
      resetSelect(savedSel, "Saved vehicle cache unavailable");
    });

    function clearSavedIdentity() {
      savedSel.value = "";
      fallbackLabel = placeholderLabel;
      for (const field of ["recordId", "epaVehicleId", "year", "make", "model", "trim"]) {
        delete card.dataset[field];
      }
    }

    function rememberIdentity(vehicle, trim = "") {
      if (vehicle.record_id) card.dataset.recordId = String(vehicle.record_id);
      if (vehicle.epa_vehicle_id || vehicle.id) {
        card.dataset.epaVehicleId = String(vehicle.epa_vehicle_id || vehicle.id);
      }
      for (const field of ["year", "make", "model"]) {
        if (vehicle[field]) card.dataset[field] = String(vehicle[field]);
      }
      if (trim || vehicle.trim) card.dataset.trim = trim || vehicle.trim;
    }

    function applySavedVehicle(vehicle) {
      clearTankLookup();
      yearSel.value = "";
      resetSelect(makeSel, "Select make");
      resetSelect(modelSel, "Select model");
      resetSelect(trimSel, "Select trim");
      rememberIdentity(vehicle);
      fallbackLabel = vehicle.label || placeholderLabel;
      labelEl.textContent = fallbackLabel;
      cityInput.value = vehicle.city_l_100km || "";
      highwayInput.value = vehicle.highway_l_100km || "";
      if (vehicle.fuel_type && vehicle.fuel_type !== "unsupported") {
        fuelSel.value = vehicle.fuel_type;
      }
      tankInput.value = vehicle.tank_size || "";
      tankUnitSel.value = vehicle.tank_unit || "liter";
      note.hidden = true;
      if (vehicle.fuel_type === "unsupported") {
        note.hidden = false;
        note.textContent = "This saved vehicle's fuel type isn't supported. Select a fuel type manually.";
      }
      if (vehicle.tank_size) {
        setTankHint("Loaded from the local vehicle cache. You can edit any value before comparing.");
      } else {
        setTankHint(
          "Loaded vehicle data from the local cache. Enter the tank size manually.",
          fuelTankCapVehicleUrl(vehicle.make, vehicle.base_model || vehicle.model, vehicle.year)
        );
      }
    }

    savedSel.addEventListener("change", async () => {
      if (!savedSel.value) return;
      const loadSeq = ++vehicleLoadSeq;
      try {
        const vehicle = await fetchJSON(`/api/saved-vehicle/${encodeURIComponent(savedSel.value)}`);
        if (loadSeq !== vehicleLoadSeq) return;
        applySavedVehicle(vehicle);
      } catch (err) {
        showError(err.message);
      }
    });

    yearSel.addEventListener("change", async () => {
      vehicleLoadSeq += 1;
      clearSavedIdentity();
      resetSelect(makeSel, "Select make");
      resetSelect(modelSel, "Select model");
      resetSelect(trimSel, "Select trim");
      note.hidden = true;
      clearTankLookup();
      updateLabel();
      if (!yearSel.value) return;
      try {
        const makes = await fetchJSON(`/api/makes?year=${encodeURIComponent(yearSel.value)}`);
        fillSelect(makeSel, makes, "Select make");
      } catch (err) {
        showError(err.message);
      }
    });

    makeSel.addEventListener("change", async () => {
      vehicleLoadSeq += 1;
      clearSavedIdentity();
      resetSelect(modelSel, "Select model");
      resetSelect(trimSel, "Select trim");
      note.hidden = true;
      clearTankLookup();
      updateLabel();
      if (!makeSel.value) return;
      try {
        const models = await fetchJSON(
          `/api/models?year=${encodeURIComponent(yearSel.value)}&make=${encodeURIComponent(makeSel.value)}`
        );
        fillSelect(modelSel, models, "Select model");
      } catch (err) {
        showError(err.message);
      }
    });

    modelSel.addEventListener("change", async () => {
      vehicleLoadSeq += 1;
      clearSavedIdentity();
      resetSelect(trimSel, "Select trim");
      note.hidden = true;
      clearTankLookup();
      updateLabel();
      if (!modelSel.value) return;
      try {
        const trims = await fetchJSON(
          `/api/trims?year=${encodeURIComponent(yearSel.value)}&make=${encodeURIComponent(makeSel.value)}&model=${encodeURIComponent(modelSel.value)}`
        );
        fillSelect(trimSel, trims, "Select trim");
      } catch (err) {
        showError(err.message);
      }
    });

    trimSel.addEventListener("change", async () => {
      const loadSeq = ++vehicleLoadSeq;
      clearSavedIdentity();
      note.hidden = true;
      clearTankLookup();
      updateLabel();
      if (!trimSel.value) return;
      try {
        const v = await fetchJSON(`/api/vehicle/${encodeURIComponent(trimSel.value)}`);
        if (loadSeq !== vehicleLoadSeq) return;
        rememberIdentity(v, selectedText(trimSel));
        const manualTankLookupUrl = fuelTankCapVehicleUrl(
          v.make,
          v.base_model || v.model,
          v.year
        );
        if (v.city_l_100km) cityInput.value = v.city_l_100km;
        if (v.highway_l_100km) highwayInput.value = v.highway_l_100km;
        if (v.fuel_type && v.fuel_type !== "unsupported") {
          fuelSel.value = v.fuel_type;
        }
        if (v.fuel_type === "unsupported") {
          note.hidden = false;
          note.textContent = `This vehicle's fuel type (${v.fuel_type_label || "unknown"}) isn't supported for cost comparison. Pick a gasoline or diesel trim, or set the fields manually.`;
        }

        if (v.tank_size) {
          tankInput.value = v.tank_size;
          tankUnitSel.value = v.tank_unit || "liter";
          setTankHint("Loaded tank size from the local vehicle cache. You can edit it if needed.");
          return;
        }

        // Tank capacity isn't in the EPA data, so match its vehicle record to
        // CarAPI. Keep all candidate sizes available as datalist suggestions.
        setTankHint("Looking up tank size…");
        try {
          const params = new URLSearchParams({
            year: v.year, make: v.make, model: v.model,
            cylinders: v.cylinders || "", displ: v.displ || "",
            city_mpg: v.city_mpg || "", highway_mpg: v.highway_mpg || "",
            transmission: v.trany || "", base_model: v.base_model || "",
            vehicle_id: v.epa_vehicle_id || v.id || trimSel.value,
          });
          const tank = await fetchJSON(`/api/tank-size?${params}`);
          if (loadSeq !== vehicleLoadSeq) return;
          for (const match of (tank && tank.matches) || []) {
            const option = document.createElement("option");
            option.value = match.capacity_l;
            option.label = match.matched_trim;
            tankOptions.appendChild(option);
          }
          if (tank && tank.capacity_l) {
            tankInput.value = tank.capacity_l;
            tankUnitSel.value = "liter";
            setTankHint(
              tank.cached
                ? "Loaded tank size from the local vehicle cache. You can edit it if needed."
                : tank.matched_trim
                ? `Estimated from ${tank.matched_trim} via CarAPI — verify against your owner's manual.`
                : "Estimated via CarAPI — verify against your owner's manual."
            );
          } else if (tank && tank.matches && tank.matches.length) {
            setTankHint(
              "Several tank sizes match. Choose a suggestion based on the exact trim, or enter it manually.",
              manualTankLookupUrl
            );
          } else {
            setTankHint(
              "No automatic tank-size match found. Enter it manually.",
              manualTankLookupUrl
            );
          }
        } catch (_tankErr) {
          if (loadSeq !== vehicleLoadSeq) return;
          setTankHint(
            "Tank-size lookup is unavailable. Enter it manually.",
            manualTankLookupUrl
          );
        }
      } catch (err) {
        showError(err.message);
      }
    });

    card.querySelector(".btn-remove").addEventListener("click", () => {
      card.remove();
    });

    vehiclesEl.appendChild(frag);
  }

  document.getElementById("add-vehicle").addEventListener("click", () => addVehicleCard());

  function collectPayload() {
    const distance = {
      value: parseFloat(document.getElementById("distance-value").value),
      unit: document.getElementById("distance-unit").value,
      period: document.getElementById("distance-period").value,
    };
    const cityShare = parseInt(splitSlider.value, 10);
    const weighting = {
      city: cityShare,
      highway: 100 - cityShare,
    };
    const price_unit = document.getElementById("price-unit").value;
    const prices = {
      regular: parseFloat(document.getElementById("price-regular").value),
      midgrade: parseFloat(document.getElementById("price-midgrade").value),
      premium: parseFloat(document.getElementById("price-premium").value),
      diesel: parseFloat(document.getElementById("price-diesel").value),
    };

    const vehicles = Array.from(document.querySelectorAll(".vehicle-card")).map((card) => ({
      label: card.querySelector(".v-label").textContent,
      record_id: card.dataset.recordId || "",
      epa_vehicle_id: card.dataset.epaVehicleId || "",
      year: card.dataset.year || card.querySelector(".v-year").value,
      make: card.dataset.make || card.querySelector(".v-make").value,
      model: card.dataset.model || card.querySelector(".v-model").value,
      trim: card.dataset.trim || (
        card.querySelector(".v-trim").value
          ? card.querySelector(".v-trim").options[card.querySelector(".v-trim").selectedIndex].text
          : ""
      ),
      city_l_100km: parseFloat(card.querySelector(".v-city").value),
      highway_l_100km: parseFloat(card.querySelector(".v-highway").value),
      fuel_type: card.querySelector(".v-fuel").value,
      tank_size: parseFloat(card.querySelector(".v-tank").value),
      tank_unit: card.querySelector(".v-tank-unit").value,
    }));

    return { distance, weighting, price_unit, prices, vehicles };
  }

  function renderResults(data) {
    const rows = data.vehicles
      .map((v) => {
        const cheapest = v.label === data.cheapest_label;
        const delta = v.delta_vs_cheapest > 0 ? `+$${v.delta_vs_cheapest.toFixed(2)}` : "—";
        return `<tr class="${cheapest ? "cheapest" : ""}">
          <td>${v.label}</td>
          <td>${v.overall_l_100km.toFixed(2)}</td>
          <td>${v.range_km.toFixed(0)}</td>
          <td>$${v.cost_per_tank.toFixed(2)}</td>
          <td>${v.fillups_per_year.toFixed(1)}</td>
          <td>$${v.annual_cost.toFixed(2)}</td>
          <td>${delta}</td>
        </tr>`;
      })
      .join("");

    resultsEl.innerHTML = `
      <p class="results-summary">${data.annual_km.toLocaleString()} km/year &middot; ${data.city_weight}% city / ${data.highway_weight}% highway</p>
      <table>
        <thead>
          <tr>
            <th>Vehicle</th>
            <th>L/100km</th>
            <th>Range (km)</th>
            <th>Cost/tank</th>
            <th>Fill-ups/yr</th>
            <th>Annual cost</th>
            <th>vs cheapest</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    `;
  }

  document.getElementById("run-compare").addEventListener("click", async () => {
    showError(null);
    resultsEl.innerHTML = "";
    try {
      const payload = collectPayload();
      const data = await fetchJSON("/api/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      renderResults(data);
      refreshSavedVehicles().catch(() => {});
    } catch (err) {
      showError(err.message);
    }
  });

  addVehicleCard("Vehicle A");
  addVehicleCard("Vehicle B");
})();
