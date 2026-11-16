import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/api_client.dart';
import '../data/inventory_models.dart';
import '../data/inventory_repository.dart';

final inventoryRepositoryProvider = Provider<InventoryRepository>(
    (ref) => InventoryRepository(ref.watch(apiClientProvider)));

/// Every stock row (Req 21.1). Low-stock alerts and the count are derived
/// from it (Req 21.9).
final inventoryProvider = FutureProvider.autoDispose<List<StockItem>>(
    (ref) => ref.watch(inventoryRepositoryProvider).list());

final stockHistoryProvider = FutureProvider.autoDispose
    .family<List<StockAdjustment>, String>(
        (ref, id) => ref.watch(inventoryRepositoryProvider).history(id));
