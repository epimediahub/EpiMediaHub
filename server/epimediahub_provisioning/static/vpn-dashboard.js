"use strict";
document.getElementById("device-search")?.addEventListener("input", event => {
  const query = event.target.value.trim().toLocaleLowerCase("de");
  let shown = 0;
  document.querySelectorAll(".device[data-search]").forEach(device => {
    device.hidden = !device.dataset.search.includes(query);
    if (!device.hidden) shown++;
  });
  document.getElementById("no-search-results").hidden = shown > 0 || !query;
});
const quantity = document.getElementById("order-quantity");
const updatePrice = () => {
  if (!quantity) return;
  const count = Number(quantity.value);
  document.getElementById("order-total").textContent = Number.isInteger(count) && count > 0 && count <= 10000
    ? "Gesamt: " + new Intl.NumberFormat("de-DE", {style:"currency",currency:"EUR"}).format(count * Number(quantity.dataset.price) / 100) : "";
};
quantity?.addEventListener("input", updatePrice);
updatePrice();
document.querySelectorAll("form[data-confirm]").forEach(form => form.addEventListener("submit", event => {
  if (!window.confirm(form.dataset.confirm)) event.preventDefault();
}));
