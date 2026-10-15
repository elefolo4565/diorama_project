#include "FDBikeAudio.h"

#include <cmath>

namespace
{
	// 排気管とマフラーの共鳴 (Hz, 減衰時間 秒, 混ぜる量)。単気筒のこもった「トコトコ」になるよう低い 2 つだけにする
	constexpr float PipeLowHz = 105.f, PipeLowTau = 0.022f, PipeLowMix = 1.0f;
	constexpr float PipeMidHz = 210.f, PipeMidTau = 0.009f, PipeMidMix = 0.35f;
	constexpr float PulseDirectMix = 0.6f;  // 共鳴を通さない排気の圧力そのもの

	// 1 回の爆発の排気の圧力は、角のない山 (sin^2) にする。幅は回転が上がると周期の 55% まで縮む
	constexpr float PulseWidthMax = 0.0065f;
	constexpr float PulseNoise = 0.12f;     // 排気の息づかいのノイズ (アクセルを開けるほど多い)
	constexpr float EngineLevel = 2.0f;

	constexpr float RpmSmoothTau = 0.04f;    // 回転数の追従 (秒)
	constexpr float LoadSmoothTau = 0.06f;
	constexpr float SpeedSmoothTau = 0.1f;
	constexpr float EngineOnTau = 0.35f;     // エンジンをかける / 止めるときのフェード
	constexpr float SeaSmoothTau = 1.5f;     // 海に近づく / 離れるときの波の音のフェード

	constexpr float TwoPi = 6.28318530718f;
}

UFDBikeAudioComponent::UFDBikeAudioComponent(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	// カメラの近くで鳴っている音として、左右に振らずに鳴らす (乗っているときだけ鳴る)
	bAllowSpatialization = false;
	// AFDBikePawn の BeginPlay で Start する
	bAutoActivate = false;
}

void UFDBikeAudioComponent::FResonator::Set(float Hz, float Tau, float SampleRate)
{
	const float R = std::exp(-1.f / (Tau * SampleRate));
	const float W = TwoPi * Hz / SampleRate;
	A1 = 2.f * R * std::cos(W);
	A2 = R * R;
	InGain = std::sin(W);  // インパルスを入れたときの振幅がおよそ 1 になる
	Y1 = Y2 = 0.f;
}

float UFDBikeAudioComponent::OnePoleCoef(float Hz, float SampleRate)
{
	return 1.f - std::exp(-TwoPi * Hz / SampleRate);
}

float UFDBikeAudioComponent::Noise()
{
	// xorshift32 → -1..1
	RandState ^= RandState << 13;
	RandState ^= RandState >> 17;
	RandState ^= RandState << 5;
	return static_cast<float>(RandState) * (2.f / 4294967295.f) - 1.f;
}

bool UFDBikeAudioComponent::Init(int32& SampleRate)
{
	NumChannels = 1;
	Rate = static_cast<float>(FMath::Max(SampleRate, 8000));
	PipeLow.Set(PipeLowHz, PipeLowTau, Rate);
	PipeMid.Set(PipeMidHz, PipeMidTau, Rate);
	return true;
}

void UFDBikeAudioComponent::SetState(float InRpm, float InLoad, float InSpeedMs, bool bEngineOn, float InWindScale, float InSeaAmount)
{
	TargetRpm.store(FMath::Clamp(InRpm, 300.f, 10000.f), std::memory_order_relaxed);
	TargetLoad.store(FMath::Clamp(InLoad, 0.f, 1.f), std::memory_order_relaxed);
	TargetSpeed.store(FMath::Max(InSpeedMs, 0.f), std::memory_order_relaxed);
	TargetEngineOn.store(bEngineOn ? 1.f : 0.f, std::memory_order_relaxed);
	TargetWindScale.store(FMath::Max(InWindScale, 0.f), std::memory_order_relaxed);
	TargetSea.store(FMath::Clamp(InSeaAmount, 0.f, 1.f), std::memory_order_relaxed);
	EngineGain.store(bEngineSound ? EngineVolume : 0.f, std::memory_order_relaxed);
	WaveGain.store(bWaveSound ? WaveVolume : 0.f, std::memory_order_relaxed);
	WindGain.store(bWindSound ? WindVolume : 0.f, std::memory_order_relaxed);
}

int32 UFDBikeAudioComponent::OnGenerateAudio(float* OutAudio, int32 NumSamples)
{
	const float TRpm = TargetRpm.load(std::memory_order_relaxed);
	const float TLoad = TargetLoad.load(std::memory_order_relaxed);
	const float TSpeed = TargetSpeed.load(std::memory_order_relaxed);
	const float TOn = TargetEngineOn.load(std::memory_order_relaxed);
	const float TWind = TargetWindScale.load(std::memory_order_relaxed);
	const float TSea = TargetSea.load(std::memory_order_relaxed);
	const float EngineMix = EngineGain.load(std::memory_order_relaxed);
	const float WaveMix = WaveGain.load(std::memory_order_relaxed);
	const float WindMix = WindGain.load(std::memory_order_relaxed);

	const float KRpm = 1.f - std::exp(-1.f / (RpmSmoothTau * Rate));
	const float KLoad = 1.f - std::exp(-1.f / (LoadSmoothTau * Rate));
	const float KSpeed = 1.f - std::exp(-1.f / (SpeedSmoothTau * Rate));
	const float KOn = 1.f - std::exp(-1.f / (EngineOnTau * Rate));
	const float PulseNorm = 1.f / (0.5f * PulseWidthMax * Rate);
	const float KRumble = OnePoleCoef(35.f, Rate);
	const float KWind = OnePoleCoef(260.f, Rate);
	const float KSea = 1.f - std::exp(-1.f / (SeaSmoothTau * Rate));
	const float Dt = 1.f / Rate;

	for (int32 i = 0; i < NumSamples; ++i)
	{
		Rpm += (TRpm - Rpm) * KRpm;
		Load += (TLoad - Load) * KLoad;
		Speed += (TSpeed - Speed) * KSpeed;
		EngineOn += (TOn - EngineOn) * KOn;
		WindScale += (TWind - WindScale) * KSpeed;
		Sea += (TSea - Sea) * KSea;

		// ---- エンジン: 2 回転に 1 回の爆発で、排気管の共鳴を叩く
		float Engine = 0.f;
		if (EngineOn > 0.001f)
		{
			// アイドリングに近いほど爆発の間隔と強さがばらつく (単気筒らしい不規則さ)
			const float IdleT = FMath::Clamp((2600.f - Rpm) / 1400.f, 0.f, 1.f);
			CyclePhase += Rpm / 120.f * Dt * (1.f + NextJitter);
			if (CyclePhase >= 1.f)
			{
				CyclePhase -= 1.f;
				NextJitter = Noise() * (0.02f + 0.08f * IdleT);
				FireAmp = (0.5f + 0.5f * Load) * (1.f + Noise() * (0.06f + 0.14f * IdleT));
				PulseTime = 0.f;
				PulseWidth = FMath::Min(PulseWidthMax, 0.55f * 120.f / FMath::Max(Rpm, 300.f));
			}
			float Pulse = 0.f;
			if (PulseTime < PulseWidth)
			{
				Pulse = FireAmp * FMath::Square(std::sin(UE_PI * PulseTime / PulseWidth));
				PulseTime += Dt;
			}
			// 山の面積で割って、サンプリング周波数によらない強さにする
			const float Excite = (Pulse + Noise() * Pulse * PulseNoise * (0.3f + 0.7f * Load)) * PulseNorm;
			const float Pipe = PipeLow.Process(Excite) * PipeLowMix + PipeMid.Process(Excite) * PipeMidMix + Pulse * PulseDirectMix;

			// マフラー (2 段のローパス)。アクセルを開けるほど、回るほど明るくなる
			const float KMuffler = OnePoleCoef(300.f + 700.f * Load + 0.10f * Rpm, Rate);
			MufflerLp1 += (Pipe - MufflerLp1) * KMuffler;
			MufflerLp2 += (MufflerLp1 - MufflerLp2) * KMuffler;

			// 回るほど爆発の回数が増えて大きくなるので、そのぶんを抑える
			Engine = MufflerLp2 * EngineLevel * std::sqrt(1500.f / FMath::Max(Rpm, 800.f));
		}
		// 直流を切る
		DcOut = Engine - DcIn + 0.995f * DcOut;
		DcIn = Engine;
		Engine = DcOut * EngineOn * EngineMix;

		// ---- 波: 海の近くでだけ鳴る。数秒ごとに寄せて (大きく明るく) 引く (小さくこもる)。速度には関係しない
		float WaveOut = 0.f;
		if (Sea > 0.001f && WaveMix > 0.f)
		{
			WavePhase += Dt / WavePeriod;
			if (WavePhase >= 1.f)
			{
				WavePhase -= 1.f;
				WavePeriod = 6.5f + 2.5f * Noise();  // 4-9 秒
			}
			// 前の 25% で崩れて大きくなり、残りで引いていく。引いているあいだも少しざわめきが残る
			const float Swell = WavePhase < 0.25f ? FMath::SmoothStep(0.f, 1.f, WavePhase / 0.25f)
			                                      : std::exp(-(WavePhase - 0.25f) * 4.f);
			const float Env = 0.18f + 0.82f * Swell;
			const float KWave = OnePoleCoef(250.f + 1400.f * Swell, Rate);
			WaveLp1 += (Noise() - WaveLp1) * KWave;
			WaveLp2 += (WaveLp1 - WaveLp2) * KWave;
			// 低くしたノイズは小さくなるので、カットオフに応じて大きさをそろえる
			const float Hiss = WaveLp2 * (1.f / std::sqrt(KWave)) * 0.55f;
			WaveRumbleLp += (Noise() - WaveRumbleLp) * KRumble;
			const float Rumble = WaveRumbleLp * (1.f / std::sqrt(KRumble)) * 0.5f;
			WaveOut = (Hiss + Rumble * 0.5f) * Env * Sea * WaveMix;
		}

		// ---- 風切り: 速度に比例する低いノイズ (ヘルメットの中は大きい)
		const float V = Speed;
		WindLp1 += (Noise() - WindLp1) * KWind;
		WindLp2 += (WindLp1 - WindLp2) * KWind;
		const float WindOut = WindLp2 * (1.f / std::sqrt(KWind)) * 0.5f * FMath::Min(V / 20.f, 1.3f) * WindScale * WindMix;

		const float Mix = Engine + WaveOut + WindOut;
		OutAudio[i] = std::tanh(Mix);
	}
	return NumSamples;
}
