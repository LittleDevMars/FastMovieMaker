"""FFmpeg xfade 필터를 이용한 클립 간 트랜지션 생성 서비스."""

class TransitionService:
    @staticmethod
    def build_xfade_filter(clip_a_name: str, clip_b_name: str, 
                          clip_a_duration_sec: float, 
                          transition_type: str = "fade", 
                          duration_sec: float = 1.0) -> str:
        """
        두 비디오 스트림 간의 xfade 필터 문자열을 생성합니다.
        
        Args:
            clip_a_name: 첫 번째 클립의 라벨 (예: [v0])
            clip_b_name: 두 번째 클립의 라벨 (예: [v1])
            clip_a_duration_sec: 첫 번째 클립의 전체 길이(초)
            transition_type: 트랜지션 효과 (fade, dissolve, wipeleft 등)
            duration_sec: 트랜지션 지속 시간(초)
            
        Returns:
            FFmpeg filter_complex 문자열
        """
        # 트랜지션 시작 시점 계산: 첫 클립이 끝나기 duration_sec 전부터 시작
        offset = max(0, clip_a_duration_sec - duration_sec)
        
        return (f"{clip_a_name}{clip_b_name}xfade="
                f"transition={transition_type}:"
                f"duration={duration_sec}:"
                f"offset={offset}")

    @staticmethod
    def build_acrossfade_filter(audio_a_name: str, audio_b_name: str, 
                               duration_sec: float = 1.0) -> str:
        """
        두 오디오 스트림 간의 acrossfade 필터 문자열을 생성합니다.
        """
        return f"{audio_a_name}{audio_b_name}acrossfade=d={duration_sec}"

    @staticmethod
    def get_available_transitions():
        """FFmpeg xfade에서 지원하는 주요 트랜지션 목록을 반환합니다."""
        return [
            "fade", "dissolve", "wipeleft", "wiperight", "wipeup", "wipedown",
            "slideleft", "slideright", "slideup", "slidedown",
            "circlecrop", "rectcrop", "distance", "pixelize"
        ]