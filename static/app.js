(() => {
  "use strict";

  const vehiclesEl = document.getElementById("vehicles");
  const template = document.getElementById("vehicle-card-template");
  const errorBox = document.getElementById("error-box");
  const resultsEl = document.getElementById("results");
  let vehicleSeq = 0;
  let yearsCache = null;

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

  function addVehicleCard(defaultLabel) {
    const index = vehicleSeq++;
    const frag = template.content.cloneNode(true);
    const card = frag.querySelector(".vehicle-card");
    card.dataset.index = String(index);

    const labelEl = card.querySelector(".v-label");
    const placeholderLabel = defaultLabel || `Vehicle ${index + 1}`;

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
        labelEl.textContent = placeholderLabel;
      }
    }
    updateLabel();

    ensureYears(yearSel).catch((err) => showError(err.message));

    yearSel.addEventListener("change", async () => {
      vehicleLoadSeq += 1;
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
      note.hidden = true;
      clearTankLookup();
      updateLabel();
      if (!trimSel.value) return;
      try {
        const v = await fetchJSON(`/api/vehicle/${encodeURIComponent(trimSel.value)}`);
        if (loadSeq !== vehicleLoadSeq) return;
        if (v.city_l_100km) cityInput.value = v.city_l_100km;
        if (v.highway_l_100km) highwayInput.value = v.highway_l_100km;
        if (v.fuel_type && v.fuel_type !== "unsupported") {
          fuelSel.value = v.fuel_type;
        }
        if (v.fuel_type === "unsupported") {
          note.hidden = false;
          note.textContent = `This vehicle's fuel type (${v.fuel_type_label || "unknown"}) isn't supported for cost comparison. Pick a gasoline or diesel trim, or set the fields manually.`;
        }

        // Tank capacity isn't in the EPA data, so match its vehicle record to
        // CarAPI. Keep all candidate sizes available as datalist suggestions.
        tankHint.hidden = false;
        tankHint.textContent = "Looking up tank size…";
        try {
          const params = new URLSearchParams({
            year: v.year, make: v.make, model: v.model,
            cylinders: v.cylinders || "", displ: v.displ || "",
            city_mpg: v.city_mpg || "", highway_mpg: v.highway_mpg || "",
            transmission: v.trany || "", base_model: v.base_model || "",
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
            tankHint.textContent = tank.matched_trim
              ? `Estimated from ${tank.matched_trim} via CarAPI — verify against your owner's manual.`
              : "Estimated via CarAPI — verify against your owner's manual.";
          } else if (tank && tank.matches && tank.matches.length) {
            tankHint.textContent = "Several tank sizes match. Choose a suggestion based on the exact trim, or enter it manually.";
          } else {
            tankHint.textContent = "No automatic tank-size match found. Enter it manually.";
          }
        } catch (_tankErr) {
          if (loadSeq !== vehicleLoadSeq) return;
          tankHint.textContent = "Tank-size lookup is unavailable. Enter it manually.";
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
    } catch (err) {
      showError(err.message);
    }
  });

  addVehicleCard("Vehicle A");
  addVehicleCard("Vehicle B");
})();
