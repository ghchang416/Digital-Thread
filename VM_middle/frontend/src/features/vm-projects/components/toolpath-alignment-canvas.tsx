import { useCallback, useEffect, useRef } from "react";

import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type {
  Point3,
  ToolpathPreviewResponse,
  ToolpathSegment,
} from "@/features/vm-projects/types/vm-project";

export type ViewMode = "iso" | "top" | "front" | "side" | "fit";

export interface StockBox {
  min: Point3;
  max: Point3;
}

export const SEGMENT_COLORS: Record<string, number> = {
  FEED: 0x4f8f12,
  RAPID: 0xb42318,
  PLUNGE: 0x0047bb,
  RETRACT: 0xa15c07,
  SKIM: 0x736273,
  LEAD_LINK: 0x8a5a00,
};

export function ToolpathAlignmentCanvas({
  stockBox,
  segments,
  bounds,
  viewMode,
}: {
  stockBox: StockBox | null;
  segments: ToolpathSegment[];
  bounds: ToolpathPreviewResponse | undefined;
  viewMode: ViewMode;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<THREE.Scene | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const contentRef = useRef<THREE.Group | null>(null);
  const boundsRef = useRef<THREE.Box3 | null>(null);

  const fitCamera = useCallback((mode: ViewMode = "fit") => {
    const camera = cameraRef.current;
    const controls = controlsRef.current;
    const boundsBox = boundsRef.current;
    if (!camera || !controls || !boundsBox || boundsBox.isEmpty()) return;

    const center = boundsBox.getCenter(new THREE.Vector3());
    const size = boundsBox.getSize(new THREE.Vector3());
    const maxSize = Math.max(size.x, size.y, size.z, 1);
    const distance = maxSize * 1.55;

    const direction =
      mode === "top"
        ? new THREE.Vector3(0, 1, 0.001)
        : mode === "front"
          ? new THREE.Vector3(0, 0.12, 1)
          : mode === "side"
            ? new THREE.Vector3(1, 0.12, 0)
            : new THREE.Vector3(1, 0.8, 1);

    camera.position.copy(center.clone().add(direction.normalize().multiplyScalar(distance)));
    camera.near = Math.max(distance / 1000, 0.01);
    camera.far = distance * 1000;
    camera.updateProjectionMatrix();
    controls.target.copy(center);
    controls.update();
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xf7f9fd);
    const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(host.clientWidth, host.clientHeight);
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

    const content = new THREE.Group();
    scene.add(content);
    scene.add(new THREE.AxesHelper(40));

    const grid = new THREE.GridHelper(200, 20, 0xb8c4d4, 0xd6dee9);
    scene.add(grid);

    sceneRef.current = scene;
    cameraRef.current = camera;
    rendererRef.current = renderer;
    controlsRef.current = controls;
    contentRef.current = content;

    const resize = () => {
      const width = Math.max(host.clientWidth, 1);
      const height = Math.max(host.clientHeight, 1);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
      renderer.setSize(width, height);
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    resize();

    let frame = 0;
    const render = () => {
      controls.update();
      renderer.render(scene, camera);
      frame = window.requestAnimationFrame(render);
    };
    render();

    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      controls.dispose();
      renderer.dispose();
      host.removeChild(renderer.domElement);
    };
  }, []);

  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;

    clearGroup(content);
    const combinedBounds = new THREE.Box3();

    if (stockBox) {
      const stockGroup = createStockBox(stockBox);
      content.add(stockGroup);
      combinedBounds.union(new THREE.Box3().setFromObject(stockGroup));
    }

    const toolpathGroup = createToolpathGroup(segments);
    content.add(toolpathGroup);
    if (segments.length) {
      combinedBounds.union(new THREE.Box3().setFromObject(toolpathGroup));
    }

    if (!combinedBounds.isEmpty()) {
      boundsRef.current = combinedBounds;
      fitCamera(viewMode);
    } else {
      boundsRef.current = null;
    }
  }, [bounds, fitCamera, segments, stockBox, viewMode]);

  useEffect(() => {
    if (viewMode) fitCamera(viewMode);
  }, [fitCamera, viewMode]);

  return <div className="stock-preview__canvas stock-preview__canvas--webgl" ref={hostRef} />;
}

function createStockBox(stockBox: StockBox) {
  const min = stockBox.min;
  const max = stockBox.max;
  const size = [
    Math.max(max[0] - min[0], 0.001),
    Math.max(max[1] - min[1], 0.001),
    Math.max(max[2] - min[2], 0.001),
  ] as const;
  const center = mapPoint([
    (min[0] + max[0]) / 2,
    (min[1] + max[1]) / 2,
    (min[2] + max[2]) / 2,
  ]);

  const group = new THREE.Group();
  const geometry = new THREE.BoxGeometry(size[0], size[2], size[1]);
  const material = new THREE.MeshBasicMaterial({
    color: 0x8b95a1,
    opacity: 0.14,
    transparent: true,
    depthWrite: false,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.copy(center);
  group.add(mesh);

  const edges = new THREE.EdgesGeometry(geometry);
  const line = new THREE.LineSegments(
    edges,
    new THREE.LineBasicMaterial({ color: 0x687386, linewidth: 1, transparent: true, opacity: 0.72 }),
  );
  line.position.copy(center);
  group.add(line);
  return group;
}

function createToolpathGroup(segments: ToolpathSegment[]) {
  const group = new THREE.Group();
  const segmentsByType = new Map<string, ToolpathSegment[]>();
  for (const segment of segments) {
    const typeSegments = segmentsByType.get(segment.type) ?? [];
    typeSegments.push(segment);
    segmentsByType.set(segment.type, typeSegments);
  }

  for (const [type, typeSegments] of segmentsByType) {
    const positions = new Float32Array(typeSegments.length * 2 * 3);
    typeSegments.forEach((segment, index) => {
      const start = mapPoint(segment.start);
      const end = mapPoint(segment.end);
      positions.set([start.x, start.y, start.z, end.x, end.y, end.z], index * 6);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({
      color: SEGMENT_COLORS[type] ?? 0x0047bb,
      transparent: true,
      opacity: type === "RAPID" ? 0.48 : 0.9,
    });
    group.add(new THREE.LineSegments(geometry, material));
  }

  return group;
}

function clearGroup(group: THREE.Group) {
  while (group.children.length) {
    const child = group.children.pop();
    if (!child) continue;
    child.traverse((object) => {
      if ("geometry" in object && object.geometry instanceof THREE.BufferGeometry) {
        object.geometry.dispose();
      }
      if ("material" in object) {
        const material = object.material;
        if (Array.isArray(material)) {
          material.forEach((item) => item.dispose());
        } else if (material instanceof THREE.Material) {
          material.dispose();
        }
      }
    });
  }
}

function mapPoint(point: Point3) {
  return new THREE.Vector3(point[0], point[2], point[1]);
}
