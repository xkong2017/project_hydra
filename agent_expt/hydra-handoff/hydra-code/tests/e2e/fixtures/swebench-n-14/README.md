# N14: Decimal Precision Loss

**Bug**: Financial calculation performs division before multiplication, losing precision.

**Fix**: Multiply before dividing, or use Decimal.
