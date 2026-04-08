/**
 * Razorpay checkout page — opened in a new tab from the extension popup.
 *
 * Reads ?plan=monthly|annual from the URL, calls the backend to create an
 * order, opens the Razorpay checkout overlay, and verifies the payment on
 * success. Closes itself on completion.
 */

import { createOrder, verifyPayment } from "../utils/api-client.js";

declare global {
  interface Window {
    Razorpay: new (options: RazorpayOptions) => RazorpayInstance;
  }
}

interface RazorpayOptions {
  key: string;
  amount: number;
  currency: string;
  name: string;
  description: string;
  order_id: string;
  handler: (response: RazorpayResponse) => void;
  modal: { ondismiss: () => void };
  theme: { color: string };
}

interface RazorpayResponse {
  razorpay_order_id: string;
  razorpay_payment_id: string;
  razorpay_signature: string;
}

interface RazorpayInstance {
  open: () => void;
}

const planInfoEl = document.querySelector<HTMLParagraphElement>("#plan-info")!;
const statusEl = document.querySelector<HTMLDivElement>("#status")!;
const spinnerEl = document.querySelector<HTMLDivElement>("#spinner")!;

function setStatus(msg: string, kind: "ok" | "err" | "" = ""): void {
  statusEl.textContent = msg;
  statusEl.className = `status ${kind}`;
}

function hideSpinner(): void {
  spinnerEl.style.display = "none";
}

async function start(): Promise<void> {
  const params = new URLSearchParams(window.location.search);
  const plan = (params.get("plan") ?? "monthly") as "monthly" | "annual";

  if (plan !== "monthly" && plan !== "annual") {
    hideSpinner();
    setStatus("Invalid plan", "err");
    return;
  }

  const planLabel = plan === "monthly" ? "Monthly — ₹499" : "Annual — ₹4,999";
  planInfoEl.textContent = `Plan: ${planLabel}`;

  let order;
  try {
    order = await createOrder(plan);
  } catch (err) {
    hideSpinner();
    setStatus(
      err instanceof Error ? err.message : "Could not create order",
      "err",
    );
    return;
  }

  hideSpinner();
  setStatus("Opening Razorpay checkout…");

  const rzp = new window.Razorpay({
    key: order.key_id,
    amount: order.amount,
    currency: order.currency,
    name: "JobCrawler",
    description: `${plan === "monthly" ? "Monthly" : "Annual"} subscription`,
    order_id: order.order_id,
    theme: { color: "#2563eb" },
    modal: {
      ondismiss: () => {
        setStatus("Checkout cancelled", "err");
      },
    },
    handler: async (response: RazorpayResponse) => {
      setStatus("Verifying payment…");
      try {
        const result = await verifyPayment({
          razorpay_order_id: response.razorpay_order_id,
          razorpay_payment_id: response.razorpay_payment_id,
          razorpay_signature: response.razorpay_signature,
        });
        setStatus(
          `Payment successful — Pro until ${new Date(result.expires_at).toLocaleDateString()}`,
          "ok",
        );
        // Close the tab after a short delay so the user sees confirmation.
        setTimeout(() => window.close(), 2500);
      } catch (err) {
        setStatus(
          err instanceof Error ? err.message : "Payment verification failed",
          "err",
        );
      }
    },
  });
  rzp.open();
}

void start();
