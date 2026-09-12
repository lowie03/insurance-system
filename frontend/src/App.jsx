import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import Checkout from "./pages/Checkout";
import PaymentResult from "./pages/PaymentResult";
import ProfileForm from "./pages/ProfileForm";
import Recommendations from "./pages/Recommendations";
import VerifyPolicy from "./pages/VerifyPolicy";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<ProfileForm />} />
        <Route path="/quotes/:quoteId" element={<Recommendations />} />
        <Route path="/quotes/:quoteId/checkout" element={<Checkout />} />
        <Route path="/payment" element={<PaymentResult />} />
        <Route path="/verify/:policyNumber" element={<VerifyPolicy />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
