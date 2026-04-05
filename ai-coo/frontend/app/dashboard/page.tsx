"use client";

import { useState } from "react";

import { Dashboard } from "@/components/dashboard";
import { NotificationsPage } from "@/components/notifications-page";

export default function DashboardPage() {
  const [showNotifications, setShowNotifications] = useState(false);

  if (showNotifications) {
    return <NotificationsPage onBack={() => setShowNotifications(false)} />;
  }

  return <Dashboard onOpenNotifications={() => setShowNotifications(true)} />;
}
