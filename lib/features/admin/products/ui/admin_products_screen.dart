import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../../core/money.dart';
import '../../../../core/network/app_failure.dart';
import '../../../../core/widgets/async_value_view.dart';
import '../data/admin_product_models.dart';
import '../state/admin_products_provider.dart';
import 'admin_product_form_screen.dart';

/// Staff product list with a name search, create button, activate or
/// deactivate switch and delete (Req 20.3, 20.4, 20.8, 20.9, 20.11).
class AdminProductsScreen extends ConsumerStatefulWidget {
  const AdminProductsScreen({super.key});

  @override
  ConsumerState<AdminProductsScreen> createState() =>
      _AdminProductsScreenState();
}

class _AdminProductsScreenState extends ConsumerState<AdminProductsScreen> {
  final _search = TextEditingController();
  String _query = '';

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  void _refresh() => ref.invalidate(adminProductsProvider(_query));

  void _snack(String message) => ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(SnackBar(content: Text(message)));

  Future<void> _openForm([AdminProduct? product]) async {
    final saved = await Navigator.of(context).push<bool>(MaterialPageRoute(
        builder: (_) => AdminProductFormScreen(product: product)));
    if (saved == true) _refresh();
  }

  Future<void> _toggle(AdminProduct p, bool active) async {
    try {
      await ref
          .read(adminProductsRepositoryProvider)
          .setActive(p.id, active);
      _refresh();
    } on AppFailure catch (e) {
      _snack(e.message);
    }
  }

  Future<void> _delete(AdminProduct p) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete product?'),
        content: Text('Permanently delete "${p.name}"? This cannot be undone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Delete')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(adminProductsRepositoryProvider).delete(p.id);
      _refresh();
      _snack('Product deleted');
    } on ConflictFailure {
      if (!mounted) return;
      await _offerDeactivate(p);
    } on AppFailure catch (e) {
      _snack(e.message);
    }
  }

  /// HTTP 409: the product is in an order, so recommend deactivation
  /// (Req 20.9).
  Future<void> _offerDeactivate(AdminProduct p) async {
    final deactivate = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cannot delete'),
        content: const Text(
            'This product appears in at least one order, so it cannot be '
            'deleted. Deactivate it instead to hide it from customers.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Keep active')),
          if (p.isActive)
            FilledButton(
                onPressed: () => Navigator.pop(ctx, true),
                child: const Text('Deactivate')),
        ],
      ),
    );
    if (deactivate == true) await _toggle(p, false);
  }

  @override
  Widget build(BuildContext context) {
    final products = ref.watch(adminProductsProvider(_query));
    return Scaffold(
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openForm,
        icon: const Icon(Icons.add),
        label: const Text('New product'),
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
            child: TextField(
              controller: _search,
              textInputAction: TextInputAction.search,
              decoration: InputDecoration(
                labelText: 'Search products by name',
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _query.isEmpty
                    ? null
                    : IconButton(
                        tooltip: 'Clear search',
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _search.clear();
                          setState(() => _query = '');
                        },
                      ),
              ),
              onSubmitted: (v) => setState(() => _query = v.trim()),
            ),
          ),
          Expanded(
            child: AsyncValueView<AdminProductPage>(
              value: products,
              onRetry: _refresh,
              isEmpty: (page) => page.items.isEmpty,
              emptyMessage: _query.isEmpty
                  ? 'No products yet.'
                  : 'No products match "$_query".',
              emptyActionLabel: 'New product',
              onEmptyAction: _openForm,
              errorMessage: (e) =>
                  e is AppFailure ? e.message : 'Server error',
              data: (page) => RefreshIndicator(
                onRefresh: () async => _refresh(),
                child: ListView.separated(
                  padding: const EdgeInsets.only(bottom: 88),
                  itemCount: page.items.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, i) => _ProductTile(
                    product: page.items[i],
                    onTap: () => _openForm(page.items[i]),
                    onToggle: (v) => _toggle(page.items[i], v),
                    onDelete: () => _delete(page.items[i]),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ProductTile extends StatelessWidget {
  const _ProductTile({
    required this.product,
    required this.onTap,
    required this.onToggle,
    required this.onDelete,
  });

  final AdminProduct product;
  final VoidCallback onTap;
  final ValueChanged<bool> onToggle;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final p = product;
    return ListTile(
      onTap: onTap,
      leading: SizedBox(
        width: 48,
        height: 48,
        child: p.firstImage == null
            ? const Icon(Icons.image_not_supported_outlined)
            : Image.network(p.firstImage!,
                fit: BoxFit.cover,
                webHtmlElementStrategy: WebHtmlElementStrategy.prefer,
                semanticLabel: p.name,
                errorBuilder: (_, __, ___) => const Icon(Icons.broken_image)),
      ),
      title: Text(p.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(
          '${formatRm(p.priceSen)} · Stock ${p.stock} · '
          '${p.isActive ? 'Active' : 'Inactive'}'),
      trailing: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Switch(
            value: p.isActive,
            onChanged: onToggle,
          ),
          IconButton(
            tooltip: 'Delete ${p.name}',
            icon: const Icon(Icons.delete_outline),
            onPressed: onDelete,
          ),
        ],
      ),
    );
  }
}
