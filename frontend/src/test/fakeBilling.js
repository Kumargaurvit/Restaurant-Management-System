import { baseRoutes } from "./helpers.jsx";

export const CATEGORIES = [{ id: 1, name: "Mains", sort_order: 0 }];
export const MENU = [
  { id: 10, category_id: 1, name: "Paneer Tikka", price: "200.00", gst_rate: "5.00", is_available: true },
  { id: 11, category_id: 1, name: "Cola", price: "50.00", gst_rate: "18.00", is_available: true },
  { id: 12, category_id: 1, name: "Sold Out Soup", price: "90.00", gst_rate: "5.00", is_available: false },
];
export const TABLES = [
  { id: 1, name: "T1", capacity: 4, is_active: true },
  { id: 2, name: "T2", capacity: 2, is_active: true },
];

/** A tiny in-memory backend: just enough behaviour to drive the billing screen. */
export function billingApi(user, { orders = [], bills = [] } = {}) {
  const state = { orders: [...orders], bills: [...bills], nextLine: 1 };
  const order = () => state.orders[state.orders.length - 1];
  const byId = (id) => state.orders.find((o) => o.id === Number(id));

  const routes = {
    ...baseRoutes(user),
    "GET /api/billing/menu/categories": CATEGORIES,
    "GET /api/billing/menu/items": MENU,
    "GET /api/billing/tables": TABLES,
    "GET /api/billing/orders": () => state.orders.filter((o) => o.status === "open"),
    "GET /api/billing/bills": () => state.bills.filter((b) => b.status === "unpaid"),
    "POST /api/billing/orders": ({ body }) => {
      const created = {
        id: state.orders.length + 1,
        order_type: body.order_type,
        status: "open",
        table_id: body.table_id ?? null,
        customer_name: body.customer_name ?? null,
        customer_phone: body.customer_phone ?? null,
        delivery_address: body.delivery_address ?? null,
        items: [],
      };
      state.orders.push(created);
      return created;
    },
  };

  // Per-order routes are registered for orders 1..3.
  for (const id of [1, 2, 3]) {
    const base = `/api/billing/orders/${id}`;
    routes[`GET ${base}`] = () => byId(id);
    routes[`POST ${base}/items`] = ({ body }) => {
      const target = byId(id);
      const menuItem = MENU.find((m) => m.id === body.menu_item_id);
      const existing = target.items.find(
        (l) => l.menu_item_id === menuItem.id && l.kitchen_ticket_id === null,
      );
      if (existing) {
        existing.quantity += body.quantity;
      } else {
        target.items.push({
          id: state.nextLine++,
          menu_item_id: menuItem.id,
          name: menuItem.name,
          unit_price: menuItem.price,
          gst_rate: menuItem.gst_rate,
          quantity: body.quantity,
          notes: null,
          kitchen_ticket_id: null,
        });
      }
      return target;
    };
    routes[`PUT ${base}/customer`] = ({ body }) => {
      const target = byId(id);
      target.customer_id = 77;
      target.customer_phone = body.phone.replace(/\D/g, "").slice(-10);
      target.customer_name = body.name ?? null;
      return target;
    };
    routes[`POST ${base}/kot`] = () => {
      byId(id).items.forEach((l) => (l.kitchen_ticket_id = 5));
      return { id: 5, order_id: id, items: [] };
    };
    routes[`POST ${base}/bill`] = ({ body }) => {
      const target = byId(id);
      target.status = "billed";
      const discount = Number(body.discount);
      const bill = {
        id: id * 10,
        invoice_number: `INV-2026-00000${id}`,
        order_id: id,
        subtotal: "500.00",
        discount: discount.toFixed(2),
        cgst: "19.00",
        sgst: "19.00",
        round_off: "0.00",
        total: (538 - discount).toFixed(2),
        status: "unpaid",
        payments: [],
        amount_paid: "0.00",
        amount_due: (538 - discount).toFixed(2),
      };
      state.bills.push(bill);
      return bill;
    };
    routes[`GET ${base}/bill`] = () => state.bills.find((b) => b.order_id === id);
    routes[`POST /api/billing/bills/${id * 10}/payments`] = ({ body }) => {
      const bill = state.bills.find((b) => b.id === id * 10);
      bill.payments.push({ id: 1, mode: body.mode, amount: body.amount, reference: body.reference });
      bill.amount_paid = Number(body.amount).toFixed(2);
      bill.amount_due = (Number(bill.total) - Number(body.amount)).toFixed(2);
      if (Number(bill.amount_due) <= 0) bill.status = "paid";
      return bill;
    };
    routes[`GET /api/billing/bills/${id * 10}/receipt`] = `RECEIPT TEXT for order ${id}\nTOTAL 538.00\n`;
  }
  routes["PATCH /api/billing/orders/1/items/1"] = ({ body }) => {
    const target = byId(1);
    if (body.quantity === 0) target.items = target.items.filter((l) => l.id !== 1);
    else target.items.find((l) => l.id === 1).quantity = body.quantity;
    return target;
  };
  routes["GET /api/billing/kot/5/print"] = "KITCHEN ORDER\n2 x Paneer Tikka\n";

  return { routes, state, order };
}
