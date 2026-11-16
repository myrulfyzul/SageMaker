import 'package:flutter/material.dart';
import '../../../core/legacy_palette.dart';
import '../../../core/widgets/section_title.dart';
import '../../catalogue/data/product.dart';
import '../../favourites/state/favourites_store.dart';
import '../../catalogue/ui/product_tile.dart';

class HomePage extends StatelessWidget {
  const HomePage({
    super.key,
    required this.products,
    required this.onShop,
    required this.onAbout,
    required this.favorites,
    required this.onProductTap,
  });
  final Future<List<Product>> products;
  final VoidCallback onShop;
  final VoidCallback onAbout;
  final FavoritesStore favorites;
  final ValueChanged<Product> onProductTap;

  @override
  Widget build(BuildContext context) => bounded(
        ListView(
          padding: const EdgeInsets.fromLTRB(18, 10, 18, 28),
          children: [
            Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                gradient: const LinearGradient(colors: [forest, deep]),
                borderRadius: BorderRadius.circular(24),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('MADE WITH PURPOSE', style: TextStyle(color: gold, fontWeight: FontWeight.w800, letterSpacing: 2, fontSize: 11)),
                  const SizedBox(height: 12),
                  const Text('Shop with impact.\nCarry a story.', style: TextStyle(color: Colors.white, fontSize: 34, height: 1.13, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 10),
                  const Text('Handcrafted gifts and everyday essentials celebrating culture, creativity, and women artisans.', style: TextStyle(color: Color(0xFFE2EDE8), height: 1.5, fontSize: 14)),
                  const SizedBox(height: 20),
                  FilledButton.icon(
                    style: FilledButton.styleFrom(backgroundColor: gold, foregroundColor: deep),
                    onPressed: onShop,
                    icon: const Icon(Icons.arrow_forward),
                    label: const Text('Explore our collection'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 28),
            const SectionTitle('Find something special'),
            const SizedBox(height: 6),
            const Text('Explore Sagemaker collections', style: TextStyle(color: Colors.black54)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _CollectionButton(label: 'Heritage Totebags', icon: Icons.shopping_bag_outlined, onTap: onShop),
                _CollectionButton(label: 'Kids & Toys', icon: Icons.toys_outlined, onTap: onShop),
                _CollectionButton(label: 'Lifestyle', icon: Icons.auto_awesome_outlined, onTap: onShop),
              ],
            ),
            const SizedBox(height: 28),
            Row(
              children: [
                const Expanded(child: SectionTitle('Featured picks')),
                TextButton(onPressed: onShop, child: const Text('See all  →')),
              ],
            ),
            const SizedBox(height: 12),
            FutureBuilder<List<Product>>(
              future: products,
              builder: (context, snapshot) {
                if (!snapshot.hasData) {
                  if (snapshot.hasError) return const Text('Catalogue unavailable');
                  return const Center(child: CircularProgressIndicator());
                }
                return SizedBox(
                  height: 240,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    itemCount: snapshot.data!.length,
                    separatorBuilder: (context, index) => const SizedBox(width: 12),
                    itemBuilder: (context, index) => SizedBox(
                      width: 195,
                      child: ProductTile(
                        product: snapshot.data![index],
                        compact: true,
                        favorites: favorites,
                        onTap: () => onProductTap(snapshot.data![index]),
                      ),
                    ),
                  ),
                );
              },
            ),
            const SizedBox(height: 26),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(18),
                child: Row(
                  children: [
                    const CircleAvatar(backgroundColor: Color(0xFFE8F2ED), child: Icon(Icons.favorite_outline, color: forest)),
                    const SizedBox(width: 12),
                    const Expanded(
                      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                        Text('More than a purchase', style: TextStyle(color: deep, fontWeight: FontWeight.w800)),
                        SizedBox(height: 3),
                        Text('Learn how Sagemaker supports creative women.', style: TextStyle(fontSize: 12, color: Colors.black54)),
                      ]),
                    ),
                    IconButton(onPressed: onAbout, icon: const Icon(Icons.north_east)),
                  ],
                ),
              ),
            ),
          ],
        ),
      );
}

class _CollectionButton extends StatelessWidget {
  const _CollectionButton({required this.label, required this.icon, required this.onTap});
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) => ActionChip(
        side: const BorderSide(color: Color(0xFFDCE6DF)),
        backgroundColor: Colors.white,
        avatar: Icon(icon, size: 17, color: forest),
        label: Text(label),
        onPressed: onTap,
      );
}

