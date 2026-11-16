import 'package:flutter/material.dart';

import '../../../core/widgets/demo_label.dart';

/// About: the prototype Demo_Label sits at the top so it is visible without
/// scrolling (Req 3.7).
class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('About')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: const [
          Align(alignment: Alignment.centerLeft, child: DemoLabel.prototype()),
          SizedBox(height: 16),
          Text('Elevating Creative Women, One Community at a Time',
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
          SizedBox(height: 12),
          Text(
              'Sagemaker highlights handcrafted products by women artisans, weaving heritage and storytelling into everyday items.'),
          SizedBox(height: 16),
          Text(
              'This is an independent demonstration app, not the official Sagemaker store. All products, prices, orders and payments are fictional.'),
        ],
      ),
    );
  }
}
