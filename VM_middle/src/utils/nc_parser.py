import re
import logging
from typing import List, Tuple, Optional, Dict

logger = logging.getLogger(__name__)

class NCParser:
    """
    NC 코드(G-Code)를 파싱하여 3D 좌표 경로(ToolPath)를 추출하는 클래스.
    """
    def __init__(self):
        # 정규식 패턴 컴파일 (X, Y, Z, F, I, J, K 값 추출용)
        self.pattern_coord = re.compile(r'([XYZFIJK])([+-]?\d*\.?\d+)')
        # G코드: G와 숫자 사이 공백 허용
        self.pattern_gcode = re.compile(r'G\s*(\d+)')

    def _read_file_lines(self, file_path: str) -> List[str]:
        """
        File reading with encoding fallback (utf-8 -> cp949 -> euc-kr).
        """
        encodings = ['utf-8', 'cp949', 'euc-kr', 'latin-1']
        for enc in encodings:
            try:
                with open(file_path, 'r', encoding=enc) as f:
                    return f.readlines()
            except UnicodeDecodeError:
                continue
            except Exception as e:
                if isinstance(e, FileNotFoundError):
                    raise e
                continue
        
        # Fallback
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            return f.readlines()

    def parse_file(self, file_path: str) -> List[Tuple[float, float, float]]:
        """
        NC 파일을 읽어 XYZ 좌표 리스트를 반환합니다.
        
        Args:
            file_path: NC 파일 경로
            
        Returns:
            List[(x, y, z)]: 3D 좌표 튜플 리스트
        """
        points = []
        
        current_x = 0.0
        current_y = 0.0
        current_z = 0.0
        
        try:
            lines = self._read_file_lines(file_path)
                
            for line in lines:
                line = line.strip().upper()
                if not line or line.startswith('(') or line.startswith('%'):
                    continue
                
                if '(' in line:
                    line = line.split('(')[0]
                
                coords = self.pattern_coord.findall(line)
                if not coords:
                    continue
                
                has_move = False
                for axis, value in coords:
                    val = float(value)
                    if axis == 'X':
                        current_x = val
                        has_move = True
                    elif axis == 'Y':
                        current_y = val
                        has_move = True
                    elif axis == 'Z':
                        current_z = val
                        has_move = True
                
                if has_move:
                    points.append((current_x, current_y, current_z))
                    
            logger.info(f"Parsed {len(points)} points from {file_path}")
            return points
            
        except Exception as e:
            logger.error(f"Failed to parse NC file {file_path}: {e}")
            return []

    def parse_as_segments(self, file_path: str) -> List[Dict]:
        """
        NC 파일을 파싱하여 세그먼트 단위의 이동 경로를 반환합니다.
        
        분류 규칙:
        - G0: 무조건 RAPID (빨강)
        - G1 상승: RETRACT (노랑)
        - G1 하강 + F최소: PLUNGE (하늘)
        - G1 수평 + RAPID/RETRACT 직후: SKIM (보라 점선)
        - G1 수평 + PLUNGE 직후: LEAD_LINK (주황)
        - G1 + RETRACT 직전: LEAD_LINK (주황)
        - 나머지 G1/G2/G3: FEED (연두)
        
        Returns:
            List[Dict]: [{'start': (x,y,z), 'end': (x,y,z), 'type': 'TYPE'}, ...]
        """
        raw_moves = []
        
        current_x = 0.0
        current_y = 0.0
        current_z = 0.0
        current_mode = 'RAPID'  # RAPID, FEED, ARC_CW(G02), ARC_CCW(G03)
        current_feedrate = None
        
        # Pass 1: 원시 데이터 수집
        try:
            lines = self._read_file_lines(file_path)
                
            for line in lines:
                line = line.strip().upper()
                if not line or line.startswith('(') or line.startswith('%'):
                    continue
                
                if '(' in line:
                    line = line.split('(')[0]
                
                # G-Code 모달 상태
                g_codes = self.pattern_gcode.findall(line)
                for g_val_str in g_codes:
                    g_val = int(g_val_str)
                    if g_val == 0:
                        current_mode = 'RAPID'
                    elif g_val == 1:
                        current_mode = 'FEED'
                    elif g_val == 2:
                        current_mode = 'ARC_CW'  # 시계방향 원호
                    elif g_val == 3:
                        current_mode = 'ARC_CCW'  # 반시계방향 원호
                
                # 좌표 및 Feed Rate, I, J, K (원호 중심 오프셋)
                coords = self.pattern_coord.findall(line)
                if not coords:
                    continue
                
                start_pt = (current_x, current_y, current_z)
                has_move = False
                arc_i, arc_j, arc_k = None, None, None
                
                for axis, value in coords:
                    val = float(value)
                    if axis == 'X':
                        current_x = val
                        has_move = True
                    elif axis == 'Y':
                        current_y = val
                        has_move = True
                    elif axis == 'Z':
                        current_z = val
                        has_move = True
                    elif axis == 'F':
                        current_feedrate = val
                    elif axis == 'I':
                        arc_i = val
                    elif axis == 'J':
                        arc_j = val
                    elif axis == 'K':
                        arc_k = val
                
                if has_move:
                    end_pt = (current_x, current_y, current_z)
                    
                    # 시작점이 원점(0,0,0)인 경우 세그먼트 생성 건너뛰기
                    # 이렇게 하면 첫 좌표 설정 명령들은 무시되고
                    # 실제 이동이 시작될 때부터 세그먼트가 생성됨
                    if abs(start_pt[0]) < 1e-6 and abs(start_pt[1]) < 1e-6 and abs(start_pt[2]) < 1e-6:
                        # 시작점이 원점이면 건너뛰기
                        continue
                    
                    move_data = {
                        'start': start_pt,
                        'end': end_pt,
                        'mode': current_mode,
                        'feedrate': current_feedrate,
                        'dx': end_pt[0] - start_pt[0],
                        'dy': end_pt[1] - start_pt[1],
                        'dz': end_pt[2] - start_pt[2]
                    }
                    
                    # 원호 정보 추가
                    if current_mode in ['ARC_CW', 'ARC_CCW']:
                        move_data['arc_i'] = arc_i if arc_i is not None else 0.0
                        move_data['arc_j'] = arc_j if arc_j is not None else 0.0
                        move_data['arc_k'] = arc_k if arc_k is not None else 0.0
                        logger.info(f"[PASS1 ARC] Adding arc to raw_moves: mode={current_mode}, start={start_pt}, end={end_pt}")
                    
                    raw_moves.append(move_data)
                    
        except Exception as e:
            logger.error(f"Pass 1 Failed: {e}")
            return []

        # Feed Rate 분석: 최소값을 Plunge로 사용
        feed_rates_g1 = sorted(set([m['feedrate'] for m in raw_moves 
                                     if m['mode'] == 'FEED' and m['feedrate'] is not None]))
        
        f_plunge = feed_rates_g1[0] if feed_rates_g1 else None
        
        logger.info(f"G1 Feed Rates: {feed_rates_g1}, Plunge F: {f_plunge}")
        
        # Pass 2: 문맥 기반 분류
        refined_segments = []
        n_moves = len(raw_moves)
        
        for i in range(n_moves):
            move = raw_moves[i]
            mode = move['mode']
            feedrate = move['feedrate']
            dx, dy, dz = move['dx'], move['dy'], move['dz']
            dist_xy = (dx**2 + dy**2)**0.5
            
            # ===== G0는 무조건 급속 이송 (빨강) =====
            if mode == 'RAPID':
                move_type = 'RAPID'
            
            # ===== G2/G3 원호 보간 =====
            elif mode in ['ARC_CW', 'ARC_CCW']:
                move_type = 'FEED'  # 원호도 FEED로 처리 (연두색)
            
            # ===== G1 분석 =====
            elif mode == 'FEED':
                # 수직 하강: PLUNGE 여부
                if dist_xy < 0.001 and dz < -0.001:
                    if f_plunge and feedrate == f_plunge:
                        move_type = 'PLUNGE'
                    else:
                        move_type = 'FEED'
                
                # 수직 상승: RETRACT
                elif dist_xy < 0.001 and dz > 0.001:
                    move_type = 'RETRACT'
                
                # 수평 이동: SKIM / LEAD / FEED 구분
                elif abs(dz) < 0.001 and dist_xy > 0.001:
                    if i > 0:
                        prev_type = refined_segments[-1]['type']
                        # RAPID 또는 RETRACT 직후 → SKIM 복구 (단, 길이 제한 적용)
                        # 짧은 구간(Step-over 등)은 가공(FEED)으로, 긴 구간만 링크(SKIM)로 표시
                        if prev_type in ['RAPID', 'RETRACT', 'SKIM']:
                            if dist_xy > 3.0: # 기준값 3.0mm
                                move_type = 'SKIM'
                            else:
                                move_type = 'FEED'
                        # PLUNGE 직후 짧은 구간 → FEED로 변경 (주황색 제거)
                        elif prev_type == 'PLUNGE':
                            move_type = 'FEED'
                        else:
                            move_type = 'FEED'
                    else:
                        move_type = 'FEED'
                
                # 3D 이동 / 아크
                else:
                    move_type = 'FEED'
                    
                    # Lead-out: 상승 직전
                    if i < n_moves - 1:
                        next_move = raw_moves[i+1]
                        next_dz = next_move['dz']
                        next_dist_xy = (next_move['dx']**2 + next_move['dy']**2)**0.5
                        
                        if next_dist_xy < 0.001 and next_dz > 0.001:
                            move_type = 'FEED'  # LEAD_LINK 대신 FEED로 변경 (주황색 제거)
            
            else:
                move_type = 'FEED'  # 기본값

            segment = {
                'start': move['start'],
                'end': move['end'],
                'type': move_type,
                'feedrate': feedrate, # 뷰어에서 램프 인식을 위해 피드값 추가
                'mode': mode  # 원호 정보를 위해 mode 저장
            }
            
            # 원호인 경우 I,J,K 파라미터 추가
            if mode in ['ARC_CW', 'ARC_CCW']:
                segment['arc_i'] = move.get('arc_i', 0.0)
                segment['arc_j'] = move.get('arc_j', 0.0)
                segment['arc_k'] = move.get('arc_k', 0.0)
                logger.info(f"[PARSER ARC] mode={mode}, I={move.get('arc_i')}, J={move.get('arc_j')}, K={move.get('arc_k')}")
            
            refined_segments.append(segment)
            
        # Pass 2 완료 - arc 세그먼트 개수 확인
        arc_count = sum(1 for s in refined_segments if s.get('mode') in ['ARC_CW', 'ARC_CCW'])
        logger.info(f"Pass 2 Complete: {len(refined_segments)} segments, {arc_count} arcs")
        
        # arc 세그먼트가 있으면 첫 번째 arc의 정보 출력
        if arc_count > 0:
            first_arc = next(s for s in refined_segments if s.get('mode') in ['ARC_CW', 'ARC_CCW'])
            logger.info(f"First ARC in refined_segments: mode={first_arc.get('mode')}, has arc_i: {'arc_i' in first_arc}")
        
        return refined_segments

    def parse_gcode_value(self, line: str) -> Optional[int]:
        """라인에서 첫 번째 G 코드를 찾아 정수값 반환 (예: G01 -> 1)"""
        match = self.pattern_gcode.search(line)
        if match:
            return int(match.group(1))
        return None
