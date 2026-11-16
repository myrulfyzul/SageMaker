import 'package:flutter/material.dart';

import '../../../core/money.dart';
import '../../../core/widgets/demo_label.dart';
import '../../favourites/ui/favourites_screen.dart';
import '../data/catalogue_models.dart';
import '../data/product.dart';

/// Product image with a Demo_Label beside demo items (Req 3.9, 8.9).
class ProductImageView extends StatelessWidget {
  const ProductImageView({super.key, required this.product});
  final CatalogueProduct product;

  @override
  Widget build(BuildContext context) {
    final url = product.firstImage;
    final placeholder = ColoredBox(
      color: Theme.of(context).colorScheme.surfaceContainerHighest,
      child: const Center(child: Icon(Icons.shopping_bag_outlined, size: 38)),
    );
    return Stack(fit: StackFit.expand, children: [
      if (url == null)
        placeholder
      else
        Image.network(url,
            fit: BoxFit.cover, errorBuilder: (_, __, ___) => placeholder),
      if (product.isDemo)
        const Positioned(left: 6, top: 6, child: DemoLabel.item()),
    ]);
  }
}

/// The favourites feature works with the lighter [Product]; this converts.
extension CatalogueProductFavourite on CatalogueProduct {
  Product toFavouriteProduct() => Product(
        id: id,
        name: name,
        category: category.name,
        description: description,
        imageUrl: firstImage ?? '',
        productUrl: '',
        priceSen: priceSen,
      );
}

class ProductCard extends StatelessWidget {
  const ProductCard({super.key, required this.product, required this.onTap});
  final CatalogueProduct product;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Stack(children: [
      Positioned.fill(child: _card(context)),
      Positioned(
        right: 2,
        top: 2,
        child: Material(
          color: Colors.white70,
          shape: const CircleBorder(),
          child: FavouriteToggle(product: product.toFavouriteProduct()),
        ),
      ),
    ]);
  }

  Widget _card(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Expanded(child: ProductImageView(product: product)),
            Padding(
              padding: const EdgeInsets.all(10),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(product.category.name.toUpperCase(),
                      style: theme.textTheme.labelSmall),
                  const SizedBox(height: 2),
                  Text(product.name,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleSmall),
                  const SizedBox(height: 4),
                  Wrap(
                    spacing: 6,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      Text(formatRm(product.priceSen),
                          style: theme.textTheme.titleSmall),
                      if (product.isDemo) const DemoLabel.item(),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(product.stockText, style: theme.textTheme.bodySmall),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
