#!/bin/bash
set -e

# Configuration
REGISTRY="${CONTAINER_REGISTRY:-your-registry.example.com}"
IMAGE_NAME="diode-discovery-agent"
TAG="${IMAGE_TAG:-latest}"
FULL_IMAGE="${REGISTRY}/${IMAGE_NAME}:${TAG}"

echo "Building Diode Discovery Agent container..."
echo "Image: ${FULL_IMAGE}"
echo ""

# Build the image
docker build -t "${FULL_IMAGE}" .

echo ""
echo "Build successful!"
echo ""
echo "To push to registry:"
echo "  docker push ${FULL_IMAGE}"
echo ""
echo "To test locally:"
echo "  docker run --rm -it \\"
echo "    -e DIODE_SERVER_URL=diode-server.netbox.svc.cluster.local:8081 \\"
echo "    -e DISCOVERY_ENABLED_METHODS=kubernetes \\"
echo "    -e LOG_LEVEL=debug \\"
echo "    ${FULL_IMAGE}"
echo ""
echo "Don't forget to update cronjob-discovery.yaml with the image name!"
