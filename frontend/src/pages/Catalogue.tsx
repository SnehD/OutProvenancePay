import { Badge, Banner, Card, Empty, ErrorNote, PageTitle, Spinner } from '../components/ui';
import { useWorkflow } from '../state/workflow';

export default function Catalogue() {
  const { products, productsError, selectedProductId, setSelectedProductId, go } = useWorkflow();
  return (
    <>
      <PageTitle title="Product Catalogue" lead="Trusted prices and sellers live on the backend. The browser can only pick a product ID." />
      <ErrorNote error={productsError} />
      {!products && !productsError && <Spinner />}
      {products && products.length === 0 && <Empty title="The catalogue is empty" />}
      {products && products.length > 0 && (
        <>
          <Banner tone="info">Some items are deliberately risky (over the limit, or from an unapproved seller) so you can watch the policy engine react.</Banner>
          <div className="grid3">
            {products.map((p) => (
              <Card key={p.id} title={p.name} subtitle={`${p.category} · ${p.seller_name}`}>
                <p className="price">{p.price} {p.currency}</p>
                <div className="row">
                  <Badge tone={p.seller_approved ? 'ok' : 'bad'}>{p.seller_approved ? 'Approved seller' : 'Unapproved seller'}</Badge>
                  {selectedProductId === p.id && <Badge tone="info">Selected</Badge>}
                </div>
                <div className="row">
                  <button className="primary" onClick={() => { setSelectedProductId(p.id); go('policy'); }}>
                    Select &amp; evaluate policy
                  </button>
                </div>
              </Card>
            ))}
          </div>
        </>
      )}
    </>
  );
}
