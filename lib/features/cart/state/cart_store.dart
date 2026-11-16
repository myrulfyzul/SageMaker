import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/storage/legacy_local_store.dart';
import '../data/guest_cart_repository.dart';

/// Resolved only after [legacyLocalStoreProvider] has loaded.
final guestCartRepositoryProvider = Provider<GuestCartRepository>(
    (ref) => GuestCartRepository(ref.watch(legacyLocalStoreProvider).requireValue));

/// Guest cart with change notification (the old `CartStore` behaviour).
class CartStore extends ChangeNotifier {
  CartStore(this._repository) : quantities = _repository.load();

  final GuestCartRepository _repository;
  final Map<String, int> quantities;

  int get count => quantities.values.fold(0, (sum, n) => sum + n);
  bool get isEmpty => quantities.isEmpty;
  int quantity(String id) => quantities[id] ?? 0;

  Future<void> setQuantity(String id, int quantity) async {
    if (quantity <= 0) {
      quantities.remove(id);
    } else {
      quantities[id] = GuestCartRepository.clampQuantity(quantity);
    }
    notifyListeners();
    await _repository.save(quantities);
  }

  Future<void> add(String id) => setQuantity(id, quantity(id) + 1);

  Future<void> clear() async {
    quantities.clear();
    notifyListeners();
    await _repository.save(quantities);
  }
}

final cartStoreProvider = Provider<CartStore>((ref) {
  final store = CartStore(ref.watch(guestCartRepositoryProvider));
  ref.onDispose(store.dispose);
  return store;
});
