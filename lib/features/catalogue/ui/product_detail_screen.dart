import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/money.dart';
import '../../../core/widgets/async_value_view.dart';
import '../../../core/widgets/error_view.dart';
import '../../../core/widgets/loading_view.dart';
import '../../favourites/ui/favourites_screen.dart';
import '../data/catalogue_models.dart';
import '../state/shop_provider.dart';
import 'product_card.dart';

/// Product detail (Req 9.10 to 9.12).
class ProductDetailScreen extends ConsumerWidget {
  const ProductDetailScreen({super.key, required this.productId});
  final String productId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final value = ref.watch(productDetailProvider(productId));
    return Scaffold(
      appBar: AppBar(title: const Text('Product details')),
      body: value.when(
        loading: () => const LoadingView(),
        error: (e, _) => ErrorView(
            message: _message(e),
            onRetry: () => ref.invalidate(productDetailProvider(productId))),
        data: (p) => ProductDetailBody(product: p),
      ),
    );
  }

  String _message(Object e) => e.toString().contains('404')
      ? 'Product not found'
      : AsyncValueView.defaultErrorMessage(e);
}

class ProductDetailBody extends ConsumerStatefulWidget {
  const ProductDetailBody({super.key, required this.product});
  final CatalogueProduct product;

  @override
  ConsumerState<ProductDetailBody> createState() => _ProductDetailBodyState();
}

class _ProductDetailBodyState extends ConsumerState<ProductDetailBody> {
  int? _variationId;

  Future<void> _add() async {
    final error =
        await ref.read(addToCartProvider)(widget.product, _variationId);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(error ?? '${widget.product.name} added to cart')));
  }

  @override
  Widget build(BuildContext context) {
    final p = widget.product;
    final theme = Theme.of(context);
    final variations = p.variations.where((v) => v.isActive).toList();
    final selected = variations.where((v) => v.id == _variationId).firstOrNull;
    final price = selected?.priceSen ?? p.priceSen;
    return ListView(padding: const EdgeInsets.all(16), children: [
      if (p.imageUrls.length > 1)
        SizedBox(
          height: 220,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: p.imageUrls.length,
            separatorBuilder: (_, __) => const SizedBox(width: 8),
            itemBuilder: (_, i) => AspectRatio(
              aspectRatio: 1.25,
              child: ProductImageView(
                  product: CatalogueProduct(
                id: p.id,
                name: p.name,
                description: p.description,
                category: p.category,
                priceSen: p.priceSen,
                isDemo: p.isDemo,
                imageUrls: [p.imageUrls[i]],
                variations: const [],
                stockLevel: p.stockLevel,
                stockQuantity: p.stockQuantity,
              )),
            ),
          ),
        )
      else
        SizedBox(height: 240, child: ProductImageView(product: p)),
      const SizedBox(height: 16),
      Text(p.category.name.toUpperCase(), style: theme.textTheme.labelMedium),
      const SizedBox(height: 4),
      Row(children: [
        Expanded(child: Text(p.name, style: theme.textTheme.headlineSmall)),
        FavouriteToggle(product: p.toFavouriteProduct()),
      ]),
      const SizedBox(height: 8),
      Wrap(
        spacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          Text(formatRm(price), style: theme.textTheme.titleLarge),
        ],
      ),
      const SizedBox(height: 8),
      Text(p.stockText,
          key: const Key('stock-status'), style: theme.textTheme.titleSmall),
      if (p.artisanName != null) ...[
        const SizedBox(height: 4),
        Text('Made by ${p.artisanName}', style: theme.textTheme.bodyMedium),
      ],
      const SizedBox(height: 12),
      Text(p.description, style: theme.textTheme.bodyMedium),
      if (variations.isNotEmpty) ...[
        const SizedBox(height: 16),
        Text('Variations', style: theme.textTheme.titleSmall),
        Wrap(spacing: 8, children: [
          for (final v in variations)
            ChoiceChip(
              label: Text('${v.label} · ${formatRm(v.priceSen)}'),
              selected: _variationId == v.id,
              onSelected: (on) =>
                  setState(() => _variationId = on ? v.id : null),
            ),
        ]),
      ],
      const SizedBox(height: 20),
      FilledButton.icon(
        key: const Key('add-to-cart'),
        onPressed: p.outOfStock ? null : _add,
        icon: const Icon(Icons.add_shopping_cart),
        label: Text(p.outOfStock ? 'Out of stock' : 'Add to cart'),
      ),
    ]);
  }
}
