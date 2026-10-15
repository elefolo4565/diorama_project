#pragma once

#include "CoreMinimal.h"
#include "Components/SynthComponent.h"
#include <atomic>
#include "FDBikeAudio.generated.h"

/**
 * クロスカブの音 (エンジン・波・風切り) をその場で合成して鳴らす。音のアセットは使わない。
 *
 * - エンジン: 空冷単気筒 4 ストローク。2 回転に 1 回の爆発ごとに、角のない排気の圧力の山で排気管とマフラーの共鳴を鳴らし、
 *   2 段のローパスでこもらせる。アイドリングでは「トコトコ」、回転が上がるとつながって「ブーン」になる。アクセルを開けるほど大きく明るい
 * - 波: 海の近くでだけ鳴る。数秒ごとに寄せては引く。速度には関係しない
 * - 風切り: 速度に比例する低いノイズ
 *
 * 値はゲームのスレッドから SetState で渡し、音のスレッド (OnGenerateAudio) でなめらかに追いかける。
 */
UCLASS(ClassGroup = (Audio), meta = (BlueprintSpawnableComponent))
class FUKUOKADRIVE_API UFDBikeAudioComponent : public USynthComponent
{
	GENERATED_BODY()

public:
	UFDBikeAudioComponent(const FObjectInitializer& ObjectInitializer);

	/** 毎フレーム呼ぶ。Rpm はエンジン回転数、Load はアクセルの開き (0-1)、SpeedMs は速度 (m/s)。
	 *  WindScale はカメラによる風切り音の倍率 (ヘルメットの中は大きい)。SeaAmount は海の近さ (0 で山の中、1 で波打ち際) */
	void SetState(float Rpm, float Load, float SpeedMs, bool bEngineOn, float WindScale, float SeaAmount);

	/** エンジン音の大きさ */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|音", meta = (ClampMin = "0", ClampMax = "2"))
	float EngineVolume = 0.6f;

	/** 波の音の大きさ */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|音", meta = (ClampMin = "0", ClampMax = "2"))
	float WaveVolume = 0.5f;

	/** 風切り音の大きさ */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|音", meta = (ClampMin = "0", ClampMax = "2"))
	float WindVolume = 0.35f;

	/** エンジン音を鳴らす (プレイ中は N キーのメニューで切り替え) */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|音")
	bool bEngineSound = true;

	/** 波の音を鳴らす */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|音")
	bool bWaveSound = true;

	/** 風切り音を鳴らす */
	UPROPERTY(EditAnywhere, BlueprintReadWrite, Category = "CrossCub|音")
	bool bWindSound = true;

protected:
	virtual bool Init(int32& SampleRate) override;
	virtual int32 OnGenerateAudio(float* OutAudio, int32 NumSamples) override;

private:
	/** 2 次の共振器 (インパルスを入れると、周波数 Hz で減衰時間 Tau 秒の正弦波になる) */
	struct FResonator
	{
		float A1 = 0.f, A2 = 0.f, InGain = 0.f;
		float Y1 = 0.f, Y2 = 0.f;
		void Set(float Hz, float Tau, float Rate);
		float Process(float X)
		{
			const float Y = InGain * X + A1 * Y1 - A2 * Y2;
			Y2 = Y1;
			Y1 = Y;
			return Y;
		}
	};

	float Noise();
	static float OnePoleCoef(float Hz, float Rate);

	// ゲームのスレッドから渡す値
	std::atomic<float> TargetRpm{1400.f};
	std::atomic<float> TargetLoad{0.f};
	std::atomic<float> TargetSpeed{0.f};
	std::atomic<float> TargetEngineOn{0.f};
	std::atomic<float> TargetWindScale{1.f};
	std::atomic<float> EngineGain{0.6f};
	std::atomic<float> TargetSea{0.f};
	std::atomic<float> WaveGain{0.5f};
	std::atomic<float> WindGain{0.35f};

	// 以下は音のスレッドだけが触る
	float Rate = 48000.f;
	uint32 RandState = 0x9E3779B9u;

	float Rpm = 1400.f;
	float Load = 0.f;
	float Speed = 0.f;
	float EngineOn = 0.f;
	float WindScale = 1.f;
	float Sea = 0.f;

	float CyclePhase = 0.f;      // 爆発の周期 (0-1)
	float FireAmp = 0.f;         // 今の爆発の強さ
	float PulseTime = 1.f;       // 今の爆発からの時間 (秒)
	float PulseWidth = 0.0065f;  // 今の爆発の排気の山の幅 (秒)
	float NextJitter = 0.f;      // 次の爆発の時期のゆらぎ

	FResonator PipeLow;          // マフラーのこもった低音
	FResonator PipeMid;          // 排気管の共鳴
	float MufflerLp1 = 0.f, MufflerLp2 = 0.f;
	float DcIn = 0.f, DcOut = 0.f;

	float WavePhase = 0.f;       // 波の周期 (0-1)
	float WavePeriod = 7.f;      // 今の波の周期 (秒)
	float WaveLp1 = 0.f, WaveLp2 = 0.f;
	float WaveRumbleLp = 0.f;
	float WindLp1 = 0.f, WindLp2 = 0.f;
};
