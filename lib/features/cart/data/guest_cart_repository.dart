import '../../../core/storage/legacy_local_store.dart';

const minLineQuantity = 1;
const maxLineQuantity = 20;

/// Guest (signed-out) cart persisted under the prototype key
/// `sagemaker_demo_cart_v1`. Quantities are clamped to 1-20 (Req 11.1, 11.12).
class GuestCartRepository {
  GuestCartRepository(this._store);

  final LegacyLocalStore _store;

  /// Product id to quantity. Lines with a quantity of 0 or less are dropped
  /// and larger quantities are capped at 20.
  Map<String, int> load() => {
        for (final e in _store.readCart().entries)
          if (e.value > 0) e.key: clampQuantity(e.value),
      };

  Future<void> save(Map<String, int> quantities) => _store.writeCart(quantities);

  /// Removes the local cart, for example after it was merged into the server cart.
  Future<void> clear() => _store.clearCart();

  static int clampQuantity(int quantity) =>
      quantity.clamp(minLineQuantity, maxLineQuantity).toInt();
}
