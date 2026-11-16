import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../checkout/data/checkout_models.dart';

/// How this server takes payments, from `GET /api/payments/config`.
class PaymentConfig {
  const PaymentConfig({
    this.gateway = 'prototype',
    this.methods = const ['fpx', 'ewallet', 'card', 'cod'],
    this.ewalletProvider,
  });

  factory PaymentConfig.fromJson(Map<String, dynamic> j) => PaymentConfig(
        gateway: (j['gateway'] as String?) ?? 'prototype',
        methods: [
          for (final m in (j['methods'] as List? ?? const [])) m.toString(),
        ],
        ewalletProvider: j['ewalletProvider'] as String?,
      );

  /// `stripe` (real hosted payment page, sandbox money) or `prototype`
  /// (simulated gateway screens inside the app).
  final String gateway;
  final List<String> methods;

  /// The only e-wallet the hosted gateway offers (GrabPay), else null.
  final String? ewalletProvider;

  bool get isHosted => gateway != 'prototype';
}

/// A payment attempt on the hosted gateway page.
class GatewayPayment {
  const GatewayPayment({
    required this.id,
    required this.status,
    required this.amountSen,
    this.orderId,
    this.checkoutUrl,
    this.message,
  });

  factory GatewayPayment.fromJson(Map<String, dynamic> j) => GatewayPayment(
        id: j['id'] as String,
        status: (j['status'] as String?) ?? 'pending',
        amountSen: (j['amountSen'] as num?)?.toInt() ?? 0,
        orderId: j['orderId'] as String?,
        checkoutUrl: j['checkoutUrl'] as String?,
        message: j['message'] as String?,
      );

  final String id;

  /// `pending`, `paid`, `cancelled`, `expired`, `failed` or `refunded`.
  final String status;
  final int amountSen;
  final String? orderId;
  final String? checkoutUrl;
  final String? message;

  bool get isPending => status == 'pending';
  bool get isPaid => status == 'paid' && orderId != null;
}

class PaymentGatewayRepository {
  PaymentGatewayRepository(this._api);
  final ApiClient _api;

  Future<PaymentConfig> config() async => PaymentConfig.fromJson(
      Map<String, dynamic>.from(await _api.get('/api/payments/config') as Map));

  Future<GatewayPayment> start({
    required String idempotencyKey,
    required DeliveryForm delivery,
    required String method,
    String? provider,
  }) async =>
      GatewayPayment.fromJson(Map<String, dynamic>.from(await _api.post(
        '/api/payments/sessions',
        body: {
          'idempotencyKey': idempotencyKey,
          'delivery': delivery.toJson(),
          'method': method,
          if (provider != null) 'provider': provider,
        },
      ) as Map));

  Future<GatewayPayment> status(String id) async =>
      GatewayPayment.fromJson(Map<String, dynamic>.from(
          await _api.get('/api/payments/sessions/$id') as Map));

  Future<GatewayPayment> cancel(String id) async =>
      GatewayPayment.fromJson(Map<String, dynamic>.from(
          await _api.post('/api/payments/sessions/$id/cancel') as Map));
}

final paymentGatewayRepositoryProvider = Provider<PaymentGatewayRepository>(
    (ref) => PaymentGatewayRepository(ref.watch(apiClientProvider)));

/// Cached for the app session. If the server cannot be reached the app falls
/// back to the prototype screens; the server still refuses anything unsafe.
final paymentConfigProvider = FutureProvider<PaymentConfig>((ref) async {
  try {
    return await ref.watch(paymentGatewayRepositoryProvider).config();
  } catch (_) {
    return const PaymentConfig();
  }
});
