import 'package:flutter/material.dart';

/// A selectable payment provider. [method] is the value the API stores
/// (`fpx`, `ewallet`, `card`, `cod`); [id] identifies the bank or wallet on
/// this device only.
class PaymentProvider {
  const PaymentProvider({
    required this.id,
    required this.name,
    required this.short,
    required this.color,
    this.onColor = Colors.white,
    this.online = true,
  });

  final String id;
  final String name;

  /// Two or three letters shown in the badge (no third-party logos).
  final String short;
  final Color color;
  final Color onColor;

  /// Offline banks are shown greyed out, as on the real FPX bank list.
  final bool online;
}

/// The payment channels offered at checkout, in display order.
enum PaymentChannel {
  fpx('fpx', 'FPX Online Banking', 'Pay from your Malaysian bank account',
      Icons.account_balance_outlined),
  ewallet('ewallet', 'E-wallet', "Touch 'n Go, GrabPay, Boost and more",
      Icons.account_balance_wallet_outlined),
  duitnow('ewallet', 'DuitNow QR', 'Scan with any banking or e-wallet app',
      Icons.qr_code_2),
  card('card', 'Credit / Debit Card', 'Visa, Mastercard, AMEX, MyDebit',
      Icons.credit_card),
  cod('cod', 'Cash on Delivery', 'Pay the courier when your parcel arrives',
      Icons.local_shipping_outlined);

  const PaymentChannel(this.method, this.label, this.subtitle, this.icon);

  /// Backend payment method.
  final String method;
  final String label;
  final String subtitle;
  final IconData icon;

  bool get needsProvider => this == fpx || this == ewallet;
}

/// FPX B2C retail banks.
const fpxBanks = <PaymentProvider>[
  PaymentProvider(id: 'maybank2u', name: 'Maybank2u', short: 'MB',
      color: Color(0xFFFFC72C), onColor: Color(0xFF1D1D1B)),
  PaymentProvider(id: 'cimb', name: 'CIMB Clicks', short: 'CI',
      color: Color(0xFFEC1C24)),
  PaymentProvider(id: 'publicbank', name: 'Public Bank', short: 'PB',
      color: Color(0xFFC8102E)),
  PaymentProvider(id: 'rhb', name: 'RHB Now', short: 'RHB',
      color: Color(0xFF005BAA)),
  PaymentProvider(id: 'hongleong', name: 'Hong Leong Connect', short: 'HL',
      color: Color(0xFF004B8D)),
  PaymentProvider(id: 'ambank', name: 'AmOnline', short: 'AM',
      color: Color(0xFFE31837)),
  PaymentProvider(id: 'bankislam', name: 'Bank Islam', short: 'BI',
      color: Color(0xFFB0005A)),
  PaymentProvider(id: 'bsn', name: 'BSN', short: 'BSN',
      color: Color(0xFF1B3F94)),
  PaymentProvider(id: 'bankrakyat', name: 'Bank Rakyat', short: 'BR',
      color: Color(0xFF00529B)),
  PaymentProvider(id: 'muamalat', name: 'Bank Muamalat', short: 'BM',
      color: Color(0xFF6D2077)),
  PaymentProvider(id: 'affin', name: 'Affin Bank', short: 'AF',
      color: Color(0xFF003F7D)),
  PaymentProvider(id: 'alliance', name: 'Alliance Bank', short: 'AL',
      color: Color(0xFF00205B)),
  PaymentProvider(id: 'agrobank', name: 'Agrobank', short: 'AG',
      color: Color(0xFF00843D)),
  PaymentProvider(id: 'hsbc', name: 'HSBC', short: 'HS',
      color: Color(0xFFDB0011)),
  PaymentProvider(id: 'ocbc', name: 'OCBC', short: 'OC',
      color: Color(0xFFD71920)),
  PaymentProvider(id: 'sc', name: 'Standard Chartered', short: 'SC',
      color: Color(0xFF0072AA)),
  PaymentProvider(id: 'uob', name: 'UOB', short: 'UOB',
      color: Color(0xFF0B3B8C)),
  PaymentProvider(id: 'kfh', name: 'KFH', short: 'KF',
      color: Color(0xFF00703C), online: false),
];

/// Popular Malaysian e-wallets.
const eWallets = <PaymentProvider>[
  PaymentProvider(id: 'tng', name: "Touch 'n Go eWallet", short: 'TnG',
      color: Color(0xFF005ABB)),
  PaymentProvider(id: 'grabpay', name: 'GrabPay', short: 'GP',
      color: Color(0xFF00B14F)),
  PaymentProvider(id: 'boost', name: 'Boost', short: 'BO',
      color: Color(0xFFEE2E24)),
  PaymentProvider(id: 'shopeepay', name: 'ShopeePay', short: 'SP',
      color: Color(0xFFEE4D2D)),
  PaymentProvider(id: 'mae', name: 'MAE by Maybank', short: 'MAE',
      color: Color(0xFFFFC72C), onColor: Color(0xFF1D1D1B)),
];

/// DuitNow QR, shown as one provider so the gateway can brand its screen.
const duitNowProvider = PaymentProvider(
    id: 'duitnow', name: 'DuitNow QR', short: 'DN', color: Color(0xFFED1C76));

/// Card networks accepted for the card form.
const cardProvider = PaymentProvider(
    id: 'card', name: 'Card', short: 'CC', color: Color(0xFF1D2A25));

List<PaymentProvider> providersFor(PaymentChannel c) => switch (c) {
      PaymentChannel.fpx => fpxBanks,
      PaymentChannel.ewallet => eWallets,
      _ => const [],
    };

PaymentProvider? providerById(String? id) {
  if (id == null) return null;
  for (final p in [...fpxBanks, ...eWallets, duitNowProvider, cardProvider]) {
    if (p.id == id) return p;
  }
  return null;
}

/// FPX B2C transaction limits in sen (RM 1.00 to RM 30,000.00).
const fpxMinSen = 100;
const fpxMaxSen = 3000000;

/// Entering this code in any OTP, TAC or PIN step simulates a decline.
const declineTestCode = '000000';

/// Card network from the leading digits, or null when unknown.
String? cardBrand(String digits) {
  if (digits.startsWith('4')) return 'VISA';
  if (RegExp(r'^(5[1-5]|2[2-7])').hasMatch(digits)) return 'Mastercard';
  if (RegExp(r'^3[47]').hasMatch(digits)) return 'AMEX';
  if (digits.startsWith('6')) return 'MyDebit';
  return null;
}

/// Luhn checksum for 13 to 19 digit card numbers.
bool luhnValid(String digits) {
  if (!RegExp(r'^\d{13,19}$').hasMatch(digits)) return false;
  var sum = 0;
  var alt = false;
  for (var i = digits.length - 1; i >= 0; i--) {
    var n = digits.codeUnitAt(i) - 48;
    if (alt) {
      n *= 2;
      if (n > 9) n -= 9;
    }
    sum += n;
    alt = !alt;
  }
  return sum % 10 == 0;
}

/// True for an `MM/YY` expiry in the current month or later.
bool expiryValid(String mmYy, [DateTime? now]) {
  final m = RegExp(r'^(\d{2})/(\d{2})$').firstMatch(mmYy);
  if (m == null) return false;
  final month = int.parse(m[1]!);
  final year = 2000 + int.parse(m[2]!);
  if (month < 1 || month > 12) return false;
  final today = now ?? DateTime.now();
  return year > today.year || (year == today.year && month >= today.month);
}
