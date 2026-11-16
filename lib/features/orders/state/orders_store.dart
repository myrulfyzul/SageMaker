import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_client.dart';
import '../../../core/storage/legacy_local_store.dart';
import '../../checkout/data/legacy_checkout_repository.dart';
import '../data/legacy_orders_repository.dart';

/// Resolved only after [legacyLocalStoreProvider] has loaded.
final legacyOrdersRepositoryProvider = Provider<LegacyOrdersRepository>((ref) =>
    LegacyOrdersRepository(
        ref.watch(legacyLocalStoreProvider).requireValue, ref.watch(apiClientProvider)));

final legacyCheckoutRepositoryProvider = Provider<LegacyCheckoutRepository>(
    (ref) => LegacyCheckoutRepository(ref.watch(apiClientProvider)));

/// Saved legacy guest orders with change notification (the old `OrdersStore`).
class OrdersStore extends ChangeNotifier {
  OrdersStore(this._repository) {
    saved.addAll(_repository.load());
  }

  final LegacyOrdersRepository _repository;
  final List<SavedOrder> saved = [];

  Future<void> add(SavedOrder value) async {
    final next = await _repository.add(saved, value);
    saved
      ..clear()
      ..addAll(next);
    notifyListeners();
  }

  Future<Map<String, dynamic>> getOrder(SavedOrder order) =>
      _repository.getOrder(order);
}

final ordersStoreProvider = Provider<OrdersStore>((ref) {
  final store = OrdersStore(ref.watch(legacyOrdersRepositoryProvider));
  ref.onDispose(store.dispose);
  return store;
});
