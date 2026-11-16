import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../data/inventory_models.dart';
import '../state/inventory_provider.dart';
import 'stock_item_sheet.dart';

/// Stock list with a low-stock alert per product and the count (Req 21.1,
/// 21.9). Tapping a row opens adjust, threshold and history (Req 21.2, 21.5,
/// 21.7).
class InventoryScreen extends ConsumerWidget {
  const InventoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final inventory = ref.watch(inventoryProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Inventory')),
      body: AsyncValueView<List<StockItem>>(
        value: inventory,
        onRetry: () => ref.invalidate(inventoryProvider),
        isEmpty: (items) => items.isEmpty,
        emptyMessage: 'No stock records yet.',
        emptyActionLabel: 'Refresh',
        onEmptyAction: () => ref.invalidate(inventoryProvider),
        errorMessage: (e) => e is AppFailure ? e.message : 'Server error',
        data: (items) {
          final low = items.where((i) => i.lowStock).toList();
          return RefreshIndicator(
            onRefresh: () async => ref.invalidate(inventoryProvider),
            child: ListView(
              children: [
                if (low.isNotEmpty)
                  Semantics(
                    liveRegion: true,
                    child: Card(
                      color: Theme.of(context).colorScheme.errorContainer,
                      margin: const EdgeInsets.all(12),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Low stock: ${low.length}',
                                style:
                                    Theme.of(context).textTheme.titleMedium),
                            for (final i in low)
                              Text(
                                  '${i.name}: ${i.quantity} left '
                                  '(threshold ${i.threshold})'),
                          ],
                        ),
                      ),
                    ),
                  ),
                for (final item in items)
                  ListTile(
                    key: ValueKey('stock-${item.productId}'),
                    title: Text(item.name),
                    subtitle: Text(
                        'Stock ${item.quantity} · Threshold ${item.threshold}'),
                    trailing: item.lowStock
                        ? Chip(
                            avatar: Icon(Icons.warning_amber,
                                size: 16,
                                color: Theme.of(context).colorScheme.error),
                            label: const Text('Low stock'))
                        : null,
                    onTap: () => showStockItemSheet(context, item),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}
