import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import 'checkout_models.dart';

/// Calls the cart (read only), address, checkout and payment-retry endpoints.
/// Only a method and a simulated outcome are sent for payment; never card
/// data (Req 13.8, 13.9).
class CheckoutRepository {
  CheckoutRepository(this._api);
  final ApiClient _api;

  Future<CheckoutCart> cart() async => CheckoutCart.fromJson(
      Map<String, dynamic>.from(await _api.get('/api/cart') as Map));

  Future<List<SavedAddress>> addresses() async {
    final raw = await _api.get('/api/me/addresses');
    return [
      for (final a in (raw as List? ?? const []))
        SavedAddress.fromJson(Map<String, dynamic>.from(a as Map)),
    ];
  }

  Future<PlacedOrder> placeOrder({
    required String idempotencyKey,
    required DeliveryForm delivery,
    required String method,
    String? outcome,
  }) async {
    final body = {
      'idempotencyKey': idempotencyKey,
      'delivery': delivery.toJson(),
      'method': method,
      if (methodNeedsOutcome(method) && outcome != null) 'outcome': outcome,
    };
    return PlacedOrder.fromJson(Map<String, dynamic>.from(
        await _api.post('/api/checkout', body: body) as Map));
  }

  Future<PlacedOrder> retryPayment(
      String orderId, String method, String? outcome) async {
    final body = {
      'method': method,
      if (methodNeedsOutcome(method) && outcome != null) 'outcome': outcome,
    };
    return PlacedOrder.fromJson(Map<String, dynamic>.from(
        await _api.post('/api/orders/$orderId/payments', body: body) as Map));
  }

  Future<PlacedOrder> order(String orderId) async => PlacedOrder.fromJson(
      Map<String, dynamic>.from(await _api.get('/api/orders/$orderId') as Map));
}

final checkoutRepositoryProvider = Provider<CheckoutRepository>(
    (ref) => CheckoutRepository(ref.watch(apiClientProvider)));

/// Thin read of `GET /api/cart` owned by checkout.
final checkoutCartProvider = FutureProvider.autoDispose<CheckoutCart>(
    (ref) => ref.watch(checkoutRepositoryProvider).cart());

/// The default saved address, or null when there is none (Req 12.5).
final defaultAddressProvider = FutureProvider.autoDispose<SavedAddress?>((ref) async {
  final all = await ref.watch(checkoutRepositoryProvider).addresses();
  for (final a in all) {
    if (a.isDefault) return a;
  }
  return null;
});

final placedOrderProvider = FutureProvider.autoDispose.family<PlacedOrder, String>(
    (ref, id) => ref.watch(checkoutRepositoryProvider).order(id));
