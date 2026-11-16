import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/money.dart';
import '../../../core/widgets/section_title.dart';
import '../../catalogue/data/product.dart';
import '../../favourites/state/favourites_store.dart';
import '../../cart/state/cart_store.dart';
import '../../favourites/ui/favorite_button.dart';
import 'product_tile.dart';

class ProductDetailPage extends StatelessWidget {
  const ProductDetailPage(
      {super.key,
      required this.product,
      required this.favorites,
      required this.cart,
      required this.onCart});
  final Product product;
  final FavoritesStore favorites;
  final CartStore cart;
  final VoidCallback onCart;

  @override
  Widget build(BuildContext context) => Scaffold(
        appBar: AppBar(
          title: const Text('Product details', style: TextStyle(color: deep)),
          actions: [
            IconButton(
              tooltip: 'Open in-app cart',
              icon: const Icon(Icons.shopping_bag_outlined),
              onPressed: onCart,
            ),
            const SizedBox(width: 8),
          ],
        ),
        body: bounded(
          ListView(
            padding: const EdgeInsets.fromLTRB(18, 12, 18, 28),
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(20),
                child: AspectRatio(
                  aspectRatio: 1.25,
                  child: ProductImage(product: product),
                ),
              ),
              const SizedBox(height: 20),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(product.category.toUpperCase(),
                            style: const TextStyle(
                                color: forest,
                                fontSize: 12,
                                fontWeight: FontWeight.w800,
                                letterSpacing: 1)),
                        const SizedBox(height: 7),
                        Text(product.name,
                            style: const TextStyle(
                                color: deep,
                                fontSize: 27,
                                fontWeight: FontWeight.w800,
                                height: 1.15)),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  FavoriteButton(product: product, favorites: favorites),
                ],
              ),
              const SizedBox(height: 16),
              Text(product.description,
                  style: const TextStyle(fontSize: 15, height: 1.55)),
              const SizedBox(height: 10),
              Text('${formatRm(product.priceSen)}  •  DEMO PRICE',
                  style: const TextStyle(
                      fontSize: 19, color: deep, fontWeight: FontWeight.w800)),
              const SizedBox(height: 10),
              const Text(
                  'Sample price only, not Sagemaker’s live price or stock.',
                  style: TextStyle(fontSize: 12, color: Colors.black54)),
              const SizedBox(height: 22),
              FilledButton.icon(
                onPressed: () async {
                  await cart.add(product.id);
                  if (context.mounted) {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text('${product.name} added to cart')));
                  }
                },
                icon: const Icon(Icons.add_shopping_cart),
                label: const Text('Add to cart'),
              ),
              const SizedBox(height: 10),
              OutlinedButton.icon(
                  onPressed: onCart,
                  icon: const Icon(Icons.shopping_bag_outlined),
                  label: const Text('View my cart')),
              const SizedBox(height: 14),
              const Text(
                  'Checkout is a simulation: no money is charged and no order goes to Sagemaker.',
                  style: TextStyle(
                      color: Colors.black54, fontSize: 12, height: 1.5)),
            ],
          ),
        ),
      );
}
